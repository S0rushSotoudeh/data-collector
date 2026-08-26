"""Small, read-only market-making quote prototype for Iran options.

The command prices one passive option order against every simple hedge path
available in the collector's current metadata and historical order books.
Only the first book level is used for taker prices and capacities.
It does not reserve resources, persist decisions, or send orders.
"""

from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import sys
from dataclasses import dataclass
from datetime import datetime, time
from typing import Literal, Sequence
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select

from src.analytics.depth import DepthBook, DepthLevel, Side
from src.analytics.parity import FEE_PRESETS
from src.db.clickhouse import get_client
from src.db.models.option import OptionInstrument
from src.db.models.stock import StockInstrument
from src.db.session import SessionLocal


TEHRAN = ZoneInfo("Asia/Tehran")
MONTH_SECONDS = (365.25 / 12) * 24 * 60 * 60
MONTHLY_RETURN_TARGET = 0.03
MULTIPLIER = 1_000
TICK_SIZE = 1
MAX_BOOK_AGE_SECONDS = 6000
MAX_CROSS_LEG_SKEW_SECONDS = 2000
EXPIRY_CUTOFF = time(12, 30)

OptionSide = Literal["buy", "sell"]
InstrumentKind = Literal["option", "stock"]


class QuoteError(ValueError):
    """Expected input or data error suitable for a concise CLI response."""


@dataclass(frozen=True)
class Contract:
    instrument_code: str
    option_type: Literal["call", "put"]
    strike: float


@dataclass(frozen=True)
class HedgeLeg:
    instrument_code: str
    side: Side
    units_per_package: int
    kind: InstrumentKind = "option"


@dataclass(frozen=True)
class Route:
    path: str
    terminal_cashflow: float
    hedge_legs: tuple[HedgeLeg, ...]
    unavailable_reason: str | None = None


def _option_type(value: str | None) -> Literal["call", "put"]:
    normalized = (value or "").strip().lower()
    if normalized in {"call", "c"}:
        return "call"
    if normalized in {"put", "p"}:
        return "put"
    raise QuoteError("target option has an unsupported option_type")


def _contract(row: OptionInstrument) -> Contract:
    if row.strike_price is None:
        raise QuoteError(f"option {row.instrument_code} has no strike")
    return Contract(row.instrument_code, _option_type(row.option_type), float(row.strike_price))


def _load_contracts(option_code: str) -> tuple[OptionInstrument, list[Contract], bool]:
    with SessionLocal() as session:
        target = session.get(OptionInstrument, option_code)
        if target is None:
            raise QuoteError(f"unknown option instrument_code: {option_code}")
        if target.underlying_instrument_code is None:
            raise QuoteError("target option has no underlying instrument_code")
        if target.expiry_date is None:
            raise QuoteError("target option has no expiry_date")
        _contract(target)
        rows = session.execute(
            select(OptionInstrument).where(
                OptionInstrument.underlying_instrument_code == target.underlying_instrument_code,
                OptionInstrument.expiry_date == target.expiry_date,
            )
        ).scalars().all()
        stock_exists = session.get(StockInstrument, target.underlying_instrument_code) is not None
        contracts = [_contract(row) for row in rows]
    return target, contracts, stock_exists


def _opposite(side: Side) -> Side:
    return "sell" if side == "buy" else "buy"


def build_routes(
    *, target: Contract, contracts: Sequence[Contract], underlying_code: str,
    maker_side: OptionSide, stock_exists: bool = True,
) -> list[Route]:
    """Enumerate direct, legal parity, and compatible one-maker box routes."""
    routes = [Route(
        path="direct", terminal_cashflow=0.0,
        hedge_legs=(HedgeLeg(target.instrument_code, _opposite(maker_side), 1),),
    )]
    by_key: dict[tuple[float, str], list[Contract]] = {}
    for contract in contracts:
        by_key.setdefault((contract.strike, contract.option_type), []).append(contract)

    counterpart_type = "put" if target.option_type == "call" else "call"
    counterparts = by_key.get((target.strike, counterpart_type), [])
    parity_allowed = (
        (target.option_type == "call" and maker_side == "sell")
        or (target.option_type == "put" and maker_side == "buy")
    )
    if not parity_allowed:
        routes.append(Route("parity", target.strike, (), f"not_allowed_for_{target.option_type}_{maker_side}"))
    elif len(counterparts) != 1:
        reason = "missing_same_strike_counterpart" if not counterparts else "ambiguous_same_strike_counterpart"
        routes.append(Route("parity", target.strike, (), reason))
    elif not stock_exists:
        routes.append(Route("parity", target.strike, (), "unknown_underlying_instrument"))
    else:
        counterpart_side: Side = "buy" if target.option_type == "call" else "sell"
        routes.append(Route(
            "parity", target.strike,
            (
                HedgeLeg(counterparts[0].instrument_code, counterpart_side, 1),
                HedgeLeg(underlying_code, "buy", MULTIPLIER, "stock"),
            ),
        ))

    if len(counterparts) == 1:
        other_strikes = sorted({contract.strike for contract in contracts if contract.strike != target.strike})
        for other_strike in other_strikes:
            other_calls = by_key.get((other_strike, "call"), [])
            other_puts = by_key.get((other_strike, "put"), [])
            if len(other_calls) != 1 or len(other_puts) != 1:
                continue
            lower = min(target.strike, other_strike)
            upper = max(target.strike, other_strike)
            target_leg = (
                "c1" if target.option_type == "call" and target.strike == lower else
                "c2" if target.option_type == "call" else
                "p1" if target.strike == lower else "p2"
            )
            long_actions: dict[str, Side] = {"c1": "buy", "c2": "sell", "p1": "sell", "p2": "buy"}
            direction = "long" if long_actions[target_leg] == maker_side else "short"
            route_actions = long_actions if direction == "long" else {
                leg: _opposite(action) for leg, action in long_actions.items()
            }
            target_counterpart = counterparts[0]
            legs_by_name = {
                ("c1" if target.strike == lower else "c2") if target.option_type == "call" else
                ("p1" if target.strike == lower else "p2"): target,
                ("p1" if target.strike == lower else "p2") if target.option_type == "call" else
                ("c1" if target.strike == lower else "c2"): target_counterpart,
                "c1" if other_strike == lower else "c2": other_calls[0],
                "p1" if other_strike == lower else "p2": other_puts[0],
            }
            hedge_legs = tuple(
                HedgeLeg(legs_by_name[name].instrument_code, route_actions[name], 1)
                for name in ("c1", "c2", "p1", "p2") if name != target_leg
            )
            terminal = upper - lower if direction == "long" else -(upper - lower)
            routes.append(Route(
                f"box:{direction}:other_strike={other_strike:g}", terminal, hedge_legs,
            ))
    if not any(route.path.startswith("box:") for route in routes):
        routes.append(Route("box", 0.0, (), "no_compatible_box_route"))
    return routes


def _hhmmss(value: datetime) -> int:
    return value.hour * 10_000 + value.minute * 100 + value.second


def _query_depth_rows(client, table: str, codes: list[str], at: datetime) -> list[tuple]:
    if not codes:
        return []
    return client.query(
        f"SELECT instrument_code, argMax(trade_time, trade_time), depth_level, "
        f"argMax(bid_price, trade_time), argMax(bid_volume, trade_time), "
        f"argMax(bid_order_count, trade_time), argMax(ask_price, trade_time), "
        f"argMax(ask_volume, trade_time), argMax(ask_order_count, trade_time) "
        f"FROM `{table}` FINAL "
        "WHERE instrument_code IN {codes:Array(String)} AND trade_date = {day:Date} "
        "AND depth_level <= 5 AND trade_time <= {end:UInt32} "
        "GROUP BY instrument_code, depth_level ORDER BY instrument_code, depth_level",
        parameters={"codes": codes, "day": at.date(), "end": _hhmmss(at)},
    ).result_rows


def reconstruct_books(rows: Sequence[tuple], at: datetime) -> dict[str, DepthBook]:
    """Carry every depth level forward; level one determines quote age."""
    levels: dict[str, dict[int, DepthLevel]] = {}
    level_one_times: dict[str, datetime] = {}
    for raw in rows:
        code, event_time, level, bid, bid_volume, bid_orders, ask, ask_volume, ask_orders = raw
        code = str(code)
        depth = DepthLevel(
            int(level), float(bid), int(bid_volume), int(bid_orders),
            float(ask), int(ask_volume), int(ask_orders),
        )
        levels.setdefault(code, {})[depth.level] = depth
        if depth.level == 1:
            value = int(event_time)
            event_clock = time(value // 10_000, (value // 100) % 100, value % 100)
            level_one_times[code] = datetime.combine(at.date(), event_clock, TEHRAN)
    return {
        code: DepthBook(level_one_times[code], tuple(by_level[key] for key in sorted(by_level)))
        for code, by_level in levels.items() if code in level_one_times
    }


def _load_books(client, routes: Sequence[Route], target_code: str, at: datetime) -> dict[str, DepthBook]:
    option_codes = {target_code}
    stock_codes: set[str] = set()
    for route in routes:
        for leg in route.hedge_legs:
            (stock_codes if leg.kind == "stock" else option_codes).add(leg.instrument_code)
    rows = _query_depth_rows(client, "option_order_book", sorted(option_codes), at)
    rows += _query_depth_rows(client, "stock_order_book", sorted(stock_codes), at)
    return reconstruct_books(rows, at)


def monthly_growth(at: datetime, expiry_at: datetime) -> float:
    seconds = max(0.0, (expiry_at - at).total_seconds())
    return (1 + MONTHLY_RETURN_TARGET) ** (seconds / MONTH_SECONDS)


def _fee_rate(kind: InstrumentKind, side: Side) -> float:
    preset = FEE_PRESETS["tse_stock" if kind == "stock" else "tse_option"]
    return preset[side]


def _signed_cost(price: float, kind: InstrumentKind, side: Side) -> float:
    rate = _fee_rate(kind, side)
    return price * (1 + rate) if side == "buy" else -price * (1 - rate)


def _route_quality(
    route: Route, target_code: str, books: dict[str, DepthBook], at: datetime,
    *, max_book_age_seconds: float = MAX_BOOK_AGE_SECONDS,
    max_cross_leg_skew_seconds: float = MAX_CROSS_LEG_SKEW_SECONDS,
    max_spread_percent: float | None = None,
) -> str | None:
    codes = {target_code, *(leg.instrument_code for leg in route.hedge_legs)}
    selected: list[DepthBook] = []
    for code in sorted(codes):
        book = books.get(code)
        if book is None:
            return f"missing_book:{code}"
        reasons = book.validation_reasons(code)
        if reasons:
            return reasons[0]
        if (at - book.source_time).total_seconds() > max_book_age_seconds:
            return f"stale_book:{code}"
        if max_spread_percent is not None:
            best = book.best
            spread_percent = 100 * (best.ask_price - best.bid_price) / best.bid_price
            if spread_percent > max_spread_percent:
                return f"wide_book:{code}"
        selected.append(book)
    if selected and (max(book.source_time for book in selected) - min(book.source_time for book in selected)).total_seconds() > max_cross_leg_skew_seconds:
        return "cross_leg_quote_skew"
    return None


def price_route(
    *, route: Route, target: Contract, maker_side: OptionSide,
    books: dict[str, DepthBook], at: datetime, expiry_at: datetime,
    max_book_age_seconds: float = MAX_BOOK_AGE_SECONDS,
    max_cross_leg_skew_seconds: float = MAX_CROSS_LEG_SKEW_SECONDS,
    max_spread_percent: float | None = None,
) -> dict[str, object]:
    result: dict[str, object] = {
        "path": route.path, "price": None, "max_quantity": 0,
        "best_bid": None, "best_ask": None,
        "price_minus_best_bid": None, "price_minus_best_ask": None,
        "maker_side_distance": None,
        "suggested_passive_price": None,
        "suggested_passive_distance": None,
        "crosses_opposite_quote": None,
        "profit_headroom_at_passive_price": None,
        "action": None,
        "execution_price": None,
        "profit_headroom_at_execution": None,
        "reason": route.unavailable_reason,
    }
    if route.unavailable_reason:
        return result
    quality_reason = _route_quality(
        route, target.instrument_code, books, at,
        max_book_age_seconds=max_book_age_seconds,
        max_cross_leg_skew_seconds=max_cross_leg_skew_seconds,
        max_spread_percent=max_spread_percent,
    )
    if quality_reason:
        result["reason"] = quality_reason
        return result

    capacity = min(
        (
            books[leg.instrument_code].best.ask_volume
            if leg.side == "buy"
            else books[leg.instrument_code].best.bid_volume
        ) // leg.units_per_package
        for leg in route.hedge_legs
    )
    result["max_quantity"] = capacity
    if capacity <= 0:
        result["reason"] = "insufficient_hedge_depth"
        return result

    hedge_cost = 0.0
    for leg in route.hedge_legs:
        price = books[leg.instrument_code].price(leg.side)
        if price is None:
            result["reason"] = f"missing_top_price:{leg.instrument_code}"
            return result
        hedge_cost += _signed_cost(price, leg.kind, leg.side)

    maker_book = books[target.instrument_code]
    best_bid = maker_book.price("sell")
    best_ask = maker_book.price("buy")
    if best_bid is None or best_ask is None:
        result["reason"] = "missing_target_spread"
        return result
    result["best_bid"] = int(best_bid)
    result["best_ask"] = int(best_ask)
    growth = monthly_growth(at, expiry_at)
    target_present_value = route.terminal_cashflow / growth
    maker_fee = _fee_rate("option", maker_side)
    if maker_side == "buy":
        boundary = (target_present_value - hedge_cost) / (1 + maker_fee)
        candidate = math.floor(boundary / TICK_SIZE) * TICK_SIZE
    else:
        boundary = (hedge_cost - target_present_value) / (1 - maker_fee)
        candidate = math.ceil(boundary / TICK_SIZE) * TICK_SIZE
    if candidate <= 0:
        result["reason"] = "calculated_price_is_not_positive"
        return result
    result["price"] = int(candidate)
    result["price_minus_best_bid"] = int(candidate - best_bid)
    result["price_minus_best_ask"] = int(candidate - best_ask)
    result["maker_side_distance"] = int(
        candidate - best_bid if maker_side == "buy" else best_ask - candidate
    )
    if maker_side == "buy":
        passive_price = min(candidate, best_ask - TICK_SIZE)
        result["suggested_passive_distance"] = int(passive_price - best_bid)
        result["crosses_opposite_quote"] = candidate >= best_ask
        result["profit_headroom_at_passive_price"] = int(candidate - passive_price)
    else:
        passive_price = max(candidate, best_bid + TICK_SIZE)
        result["suggested_passive_distance"] = int(best_ask - passive_price)
        result["crosses_opposite_quote"] = candidate <= best_bid
        result["profit_headroom_at_passive_price"] = int(passive_price - candidate)
    result["suggested_passive_price"] = int(passive_price)
    if result["crosses_opposite_quote"]:
        execution_price = best_ask if maker_side == "buy" else best_bid
        result["action"] = "immediate"
    else:
        execution_price = passive_price
        result["action"] = "passive"
    result["execution_price"] = int(execution_price)
    result["profit_headroom_at_execution"] = int(
        candidate - execution_price if maker_side == "buy" else execution_price - candidate
    )
    result["reason"] = None
    return result


def quote_paths(at: datetime, option_code: str, side: OptionSide) -> dict[str, object]:
    if at.tzinfo is None:
        at = at.replace(tzinfo=TEHRAN)
    else:
        at = at.astimezone(TEHRAN)
    target_row, contracts, stock_exists = _load_contracts(option_code)
    target = _contract(target_row)
    expiry_at = datetime.combine(target_row.expiry_date, EXPIRY_CUTOFF, TEHRAN)
    if at >= expiry_at:
        raise QuoteError("target option is expired at the requested time")
    routes = build_routes(
        target=target, contracts=contracts,
        underlying_code=str(target_row.underlying_instrument_code),
        maker_side=side, stock_exists=stock_exists,
    )
    books = _load_books(get_client(), routes, target.instrument_code, at)
    return {
        "at": at.isoformat(), "option_instrument_code": option_code, "side": side,
        "paths": [
            price_route(
                route=route, target=target, maker_side=side,
                books=books, at=at, expiry_at=expiry_at,
            )
            for route in routes
        ],
    }


def scan_market(
    at: datetime, sides: Sequence[OptionSide], *, limit: int = 50,
    competitive_only: bool = False, exclude_direct: bool = False,
    max_book_age_seconds: float = MAX_BOOK_AGE_SECONDS,
    max_cross_leg_skew_seconds: float = MAX_CROSS_LEG_SKEW_SECONDS,
    max_spread_percent: float | None = None,
) -> dict[str, object]:
    """Rank all historically eligible option routes by same-side distance."""
    if limit <= 0:
        raise QuoteError("limit must be positive")
    if at.tzinfo is None:
        at = at.replace(tzinfo=TEHRAN)
    else:
        at = at.astimezone(TEHRAN)

    with SessionLocal() as session:
        rows = session.execute(
            select(OptionInstrument).where(
                OptionInstrument.expiry_date >= at.date(),
                OptionInstrument.underlying_instrument_code.is_not(None),
                or_(OptionInstrument.listing_date.is_(None), OptionInstrument.listing_date <= at.date()),
            )
        ).scalars().all()
        underlying_codes = sorted({
            str(row.underlying_instrument_code) for row in rows
            if row.underlying_instrument_code is not None
        })
        existing_stocks = set(session.execute(
            select(StockInstrument.instrument_code).where(
                StockInstrument.instrument_code.in_(underlying_codes)
            )
        ).scalars().all())

    groups: dict[tuple[str, object], list[Contract]] = {}
    valid_rows: list[tuple[OptionInstrument, Contract]] = []
    invalid_targets = 0
    for row in rows:
        try:
            contract = _contract(row)
        except QuoteError:
            invalid_targets += 1
            continue
        expiry_at = datetime.combine(row.expiry_date, EXPIRY_CUTOFF, TEHRAN)
        if at >= expiry_at:
            continue
        key = (str(row.underlying_instrument_code), row.expiry_date)
        groups.setdefault(key, []).append(contract)
        valid_rows.append((row, contract))

    plans: list[tuple[OptionInstrument, Contract, OptionSide, list[Route]]] = []
    option_codes: set[str] = set()
    stock_codes: set[str] = set()
    for row, target in valid_rows:
        key = (str(row.underlying_instrument_code), row.expiry_date)
        for side in sides:
            routes = build_routes(
                target=target, contracts=groups[key], underlying_code=key[0],
                maker_side=side, stock_exists=key[0] in existing_stocks,
            )
            plans.append((row, target, side, routes))
            option_codes.add(target.instrument_code)
            for route in routes:
                for leg in route.hedge_legs:
                    (stock_codes if leg.kind == "stock" else option_codes).add(leg.instrument_code)

    client = get_client()
    book_rows = _query_depth_rows(client, "option_order_book", sorted(option_codes), at)
    book_rows += _query_depth_rows(client, "stock_order_book", sorted(stock_codes), at)
    books = reconstruct_books(book_rows, at)

    candidates: list[dict[str, object]] = []
    rejected = Counter()
    routes_evaluated = 0
    priced_candidates = 0
    competitive_candidates = 0
    for row, target, side, routes in plans:
        expiry_at = datetime.combine(row.expiry_date, EXPIRY_CUTOFF, TEHRAN)
        for route in routes:
            if exclude_direct and route.path == "direct":
                continue
            routes_evaluated += 1
            priced = price_route(
                route=route, target=target, maker_side=side, books=books,
                at=at, expiry_at=expiry_at,
                max_book_age_seconds=max_book_age_seconds,
                max_cross_leg_skew_seconds=max_cross_leg_skew_seconds,
                max_spread_percent=max_spread_percent,
            )
            if priced["reason"] is not None:
                reason = str(priced["reason"])
                if reason.startswith(("missing_book:", "stale_book:", "wide_book:")):
                    reason = reason.split(":", 1)[0]
                elif reason.endswith("_one_sided_or_non_positive"):
                    reason = "one_sided_or_non_positive"
                rejected[reason] += 1
                continue
            priced_candidates += 1
            distance = int(priced["maker_side_distance"])
            reference = int(priced["best_bid"] if side == "buy" else priced["best_ask"])
            distance_percent = 100 * distance / reference
            execution_price = int(priced["execution_price"])
            execution_headroom = int(priced["profit_headroom_at_execution"])
            execution_headroom_percent = 100 * execution_headroom / execution_price
            if distance >= 0:
                competitive_candidates += 1
            if competitive_only and distance < 0:
                continue
            candidates.append({
                "option_instrument_code": target.instrument_code,
                "symbol": row.symbol,
                "option_type": target.option_type,
                "strike": target.strike,
                "expiry": str(row.expiry_date),
                "side": side,
                **priced,
                "maker_side_distance_percent": round(distance_percent, 4),
                "execution_headroom_percent": round(execution_headroom_percent, 4),
                "competitive": distance >= 0,
            })

    candidates.sort(key=lambda item: (
        float(item["execution_headroom_percent"]),
        float(item["maker_side_distance_percent"]),
        int(item["maker_side_distance"]), int(item["max_quantity"]),
    ), reverse=True)
    return {
        "at": at.isoformat(),
        "sides": list(sides),
        "ranked_by": "execution_headroom_percent_then_maker_distance_desc",
        "filters": {
            "competitive_only": competitive_only,
            "exclude_direct": exclude_direct,
            "max_book_age_seconds": max_book_age_seconds,
            "max_cross_leg_skew_seconds": max_cross_leg_skew_seconds,
            "max_spread_percent": max_spread_percent,
        },
        "targets_scanned": len(valid_rows),
        "invalid_targets": invalid_targets,
        "routes_evaluated": routes_evaluated,
        "priced_candidates": priced_candidates,
        "competitive_candidates": competitive_candidates,
        "rejected_by_reason": dict(rejected.most_common()),
        "results": candidates[:limit],
    }


class _ArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise QuoteError(message)


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise QuoteError("time must be an ISO datetime such as 2026-08-12T10:30:00") from exc
    return parsed.replace(tzinfo=TEHRAN) if parsed.tzinfo is None else parsed.astimezone(TEHRAN)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _ArgumentParser(description="Price simple hedge paths for one Iran option maker quote")
    parser.add_argument("time", help="ISO Tehran datetime")
    parser.add_argument("option", help="canonical option instrument_code, or 'all'")
    parser.add_argument("side", choices=("buy", "sell", "both"), help="maker side")
    parser.add_argument("--limit", type=int, default=50, help="maximum market-scan results")
    parser.add_argument("--competitive-only", action="store_true", help="only scan results at or better than the current same-side quote")
    parser.add_argument("--exclude-direct", action="store_true", help="exclude direct target-book flatten routes from a market scan")
    parser.add_argument("--max-book-age", type=float, default=MAX_BOOK_AGE_SECONDS, help="maximum age in seconds for every route book")
    parser.add_argument("--max-cross-leg-skew", type=float, default=MAX_CROSS_LEG_SKEW_SECONDS, help="maximum timestamp difference in seconds across route books")
    parser.add_argument("--max-spread-percent", type=float, help="reject a route when any leg's bid/ask spread exceeds this percentage")
    try:
        args = parser.parse_args(argv)
        at = _parse_datetime(args.time)
        if args.option.lower() == "all":
            sides: tuple[OptionSide, ...] = ("buy", "sell") if args.side == "both" else (args.side,)
            output = scan_market(
                at, sides, limit=args.limit,
                competitive_only=args.competitive_only,
                exclude_direct=args.exclude_direct,
                max_book_age_seconds=args.max_book_age,
                max_cross_leg_skew_seconds=args.max_cross_leg_skew,
                max_spread_percent=args.max_spread_percent,
            )
        elif args.side == "both":
            raise QuoteError("side 'both' is only available when option is 'all'")
        else:
            output = quote_paths(at, args.option, args.side)
    except (QuoteError, ConnectionError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    except Exception as exc:
        print(json.dumps({"error": f"pricing failed: {exc}"}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
