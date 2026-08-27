from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Literal

from src.analytics.depth import DepthBook, Side
from src.analytics.parity import round_to_tick


BOX_CALCULATION_VERSION = "box-v2"
LEGS = ("c1", "c2", "p1", "p2")
Direction = Literal["long", "short"]

LONG_ACTIONS: dict[str, Side] = {"c1": "buy", "c2": "sell", "p1": "sell", "p2": "buy"}


def actions(direction: Direction) -> dict[str, Side]:
    if direction == "long":
        return LONG_ACTIONS
    return {leg: "sell" if side == "buy" else "buy" for leg, side in LONG_ACTIONS.items()}


def _signed_leg_cost(price: float, side: Side, buy_fee: float, sell_fee: float) -> tuple[float, float]:
    fee = price * (buy_fee if side == "buy" else sell_fee)
    return (price + fee if side == "buy" else -price + fee), fee


def _economics(
    *, direction: Direction, signed_cost: float, opening_fee: float, terminal_value: float,
    benchmark_rate: float, ttm_years: float, threshold_bps: float, feasible: bool,
) -> dict[str, Any]:
    implied_rate = None
    spread_bps = None
    review = False
    if direction == "long":
        debit = signed_cost
        credit = None
        if debit > 0 and terminal_value > 0 and ttm_years > 0:
            implied_rate = math.log(terminal_value / debit) / ttm_years
            spread_bps = (implied_rate - benchmark_rate) * 10_000
        elif debit <= 0:
            review = True
    else:
        debit = None
        credit = -signed_cost
        if credit > 0 and terminal_value > 0 and ttm_years > 0:
            implied_rate = math.log(terminal_value / credit) / ttm_years
            spread_bps = (benchmark_rate - implied_rate) * 10_000
        elif credit <= 0:
            review = True
    opportunity = bool(feasible and implied_rate is not None and spread_bps is not None and spread_bps >= threshold_bps)
    return {
        "signed_entry_cost_per_share": signed_cost,
        "entry_debit_per_share": debit,
        "entry_credit_per_share": credit,
        "opening_fee_per_share": opening_fee,
        "terminal_cashflow_per_share": terminal_value,
        "implied_rate": implied_rate,
        "benchmark_spread_bps": spread_bps,
        "opportunity": int(opportunity),
        "review_anomaly": int(review),
    }


def price_box(
    *, books: dict[str, DepthBook], lower_strike: float, upper_strike: float,
    target_boxes: int, multiplier: int, ttm_years: float, benchmark_rate: float,
    minimum_ytm_spread_bps: float, buy_fee: float, sell_fee: float,
    settlement_cost_per_contract: float, tick_size: float, calculated_at: datetime,
) -> list[dict[str, Any]]:
    if set(books) != set(LEGS):
        raise ValueError("four box legs are required")
    if lower_strike >= upper_strike or multiplier <= 0 or target_boxes <= 0 or tick_size <= 0:
        raise ValueError("invalid box inputs")
    width = upper_strike - lower_strike
    settlement_per_share = settlement_cost_per_contract / multiplier
    rows: list[dict[str, Any]] = []
    for direction in ("long", "short"):
        leg_actions = actions(direction)
        terminal = width - settlement_per_share if direction == "long" else width + settlement_per_share
        full_capacity = min(books[leg].total_volume(side) for leg, side in leg_actions.items())
        feasible = full_capacity >= target_boxes
        signed_cost = 0.0
        fees = 0.0
        direct_prices: dict[str, float | None] = {}
        for leg, side in leg_actions.items():
            price = books[leg].vwap(side, target_boxes)
            direct_prices[leg] = price
            if price is not None:
                cost, leg_fee = _signed_leg_cost(price, side, buy_fee, sell_fee)
                signed_cost += cost
                fees += leg_fee
        if any(value is None for value in direct_prices.values()):
            feasible = False
        economics = _economics(
            direction=direction, signed_cost=signed_cost, opening_fee=fees,
            terminal_value=terminal, benchmark_rate=benchmark_rate, ttm_years=ttm_years,
            threshold_bps=minimum_ytm_spread_bps, feasible=feasible,
        )
        classification = (
            "anomaly_review" if economics["review_anomaly"] else
            "executable_opportunity" if economics["opportunity"] else
            "insufficient_depth" if not feasible else "no_opportunity"
        )
        rows.append({
            "direction": direction, "execution_mode": "take_all", "maker_leg": "",
            "maker_side": "", "target_boxes": target_boxes, "capacity_boxes": full_capacity,
            "feasible": int(feasible), "benchmark_rate": benchmark_rate,
            "threshold_bps": minimum_ytm_spread_bps, "classification": classification,
            "current_maker_price": None, "queue_ahead_volume": None,
            "hedge_signed_cost_per_share": None, "target_signed_cost_per_share": None,
            "safe_maker_boundary": None, "suggested_maker_price": None, "headroom": None,
            "quality_reasons": [], "calculation_version": BOX_CALCULATION_VERSION,
            "calculated_at": calculated_at, **economics,
        })

        target_rate = benchmark_rate + minimum_ytm_spread_bps / 10_000 if direction == "long" else benchmark_rate - minimum_ytm_spread_bps / 10_000
        target_signed_cost = terminal * math.exp(-target_rate * ttm_years)
        if direction == "short":
            target_signed_cost = -target_signed_cost
        for maker_leg, maker_side in leg_actions.items():
            taker_legs = [leg for leg in LEGS if leg != maker_leg]
            capacity = min(books[leg].total_volume(leg_actions[leg]) for leg in taker_legs)
            hedge_feasible = capacity >= target_boxes
            hedge_cost = 0.0
            hedge_fees = 0.0
            for leg in taker_legs:
                side = leg_actions[leg]
                price = books[leg].vwap(side, target_boxes)
                if price is None:
                    hedge_feasible = False
                    continue
                cost, leg_fee = _signed_leg_cost(price, side, buy_fee, sell_fee)
                hedge_cost += cost
                hedge_fees += leg_fee
            fee_rate = buy_fee if maker_side == "buy" else sell_fee
            if maker_side == "buy":
                boundary = (target_signed_cost - hedge_cost) / (1 + fee_rate)
                rounded_boundary = round_to_tick(boundary, tick_size, "floor")
                best_bid = books[maker_leg].price("sell")
                best_ask = books[maker_leg].price("buy")
                suggested = min(rounded_boundary, (best_ask - tick_size) if best_ask is not None else rounded_boundary)
                quoteable = bool(hedge_feasible and best_bid is not None and suggested >= best_bid and suggested > 0)
                headroom = rounded_boundary - best_bid if best_bid is not None else None
                current_price = best_bid
            else:
                boundary = (hedge_cost - target_signed_cost) / (1 - fee_rate)
                rounded_boundary = round_to_tick(boundary, tick_size, "ceil")
                best_bid = books[maker_leg].price("sell")
                best_ask = books[maker_leg].price("buy")
                suggested = max(rounded_boundary, (best_bid + tick_size) if best_bid is not None else rounded_boundary)
                quoteable = bool(hedge_feasible and best_ask is not None and suggested <= best_ask and suggested > 0)
                headroom = best_ask - rounded_boundary if best_ask is not None else None
                current_price = best_ask
            current_cost = hedge_cost
            current_fees = hedge_fees
            if current_price is not None:
                maker_cost, maker_fee = _signed_leg_cost(current_price, maker_side, buy_fee, sell_fee)
                current_cost += maker_cost
                current_fees += maker_fee
            maker_economics = _economics(
                direction=direction, signed_cost=current_cost, opening_fee=current_fees,
                terminal_value=terminal, benchmark_rate=benchmark_rate, ttm_years=ttm_years,
                threshold_bps=minimum_ytm_spread_bps, feasible=quoteable,
            )
            maker_economics["opportunity"] = int(quoteable)
            rows.append({
                "direction": direction, "execution_mode": "one_maker", "maker_leg": maker_leg,
                "maker_side": maker_side, "target_boxes": target_boxes, "capacity_boxes": capacity,
                "feasible": int(hedge_feasible), "benchmark_rate": benchmark_rate,
                "threshold_bps": minimum_ytm_spread_bps,
                "classification": "quoteable_opportunity" if quoteable else "insufficient_depth" if not hedge_feasible else "no_opportunity",
                "current_maker_price": current_price,
                "queue_ahead_volume": books[maker_leg].queue_volume(maker_side),
                "hedge_signed_cost_per_share": hedge_cost,
                "target_signed_cost_per_share": target_signed_cost,
                "safe_maker_boundary": boundary, "suggested_maker_price": suggested,
                "headroom": headroom, "quality_reasons": [],
                "calculation_version": BOX_CALCULATION_VERSION, "calculated_at": calculated_at,
                **maker_economics,
            })
    return rows


def calculate_maker_routes(
    *, books: dict[str, DepthBook | None], direction: Direction, lower_strike: float,
    upper_strike: float, box_count: int, multiplier: int, buy_fee: float,
    sell_fee: float, settlement_cost_per_contract: float | None, tick_size: float,
    snapshot_at: datetime, expiry_at: datetime, market_data_valid: bool,
    quality_reasons: list[str],
) -> list[dict[str, Any]]:
    """Price the four one-maker/three-taker routes with a full cash-flow audit."""
    if set(books) != set(LEGS) or lower_strike >= upper_strike:
        raise ValueError("invalid box inputs")
    if box_count <= 0 or multiplier <= 0 or tick_size <= 0:
        raise ValueError("invalid box size or convention")
    leg_actions = actions(direction)
    width = upper_strike - lower_strike
    notional_units = multiplier * box_count
    settlement_total = (settlement_cost_per_contract or 0.0) * box_count
    terminal_cash_flow = (
        width * notional_units - settlement_total
        if direction == "long"
        else -width * notional_units - settlement_total
    )
    days_to_expiry = max(0.0, (expiry_at - snapshot_at).total_seconds() / 86400)
    routes: list[dict[str, Any]] = []
    for maker_leg in LEGS:
        maker_side = leg_actions[maker_leg]
        taker_legs = [leg for leg in LEGS if leg != maker_leg]
        hedge_capacity = min(
            books[leg].total_volume(leg_actions[leg]) if books[leg] is not None else 0
            for leg in taker_legs
        )
        leg_rows: list[dict[str, Any]] = []
        feasible = True
        entry_cash_flow = opening_fee = hedge_cash_flow = 0.0
        maker_price: float | None = None
        maker_queue = 0
        for leg in LEGS:
            book = books[leg]
            side = leg_actions[leg]
            role = "maker" if leg == maker_leg else "taker"
            slices: list[tuple[int, float, int]] | None
            if book is None:
                price = None
                slices = None
            elif role == "maker":
                price = book.price("sell" if side == "buy" else "buy")
                slices = [] if price is not None and price > 0 else None
                maker_price = price
                maker_queue = book.queue_volume(side)
            else:
                slices = book.fills(side, box_count)
                price = (
                    sum(slice_price * quantity for _, slice_price, quantity in slices) / box_count
                    if slices is not None else None
                )
            if price is None or price <= 0 or slices is None:
                feasible = False
                gross = fee = cash_flow = None
            else:
                gross = price * notional_units
                fee_rate = buy_fee if side == "buy" else sell_fee
                fee = gross * fee_rate
                cash_flow = -gross - fee if side == "buy" else gross - fee
                entry_cash_flow += cash_flow
                opening_fee += fee
                if role == "taker":
                    hedge_cash_flow += cash_flow
            leg_rows.append({
                "leg": leg, "role": role, "side": side, "price": price,
                "quantity": box_count,
                "available_quantity": None if role == "maker" or book is None else book.total_volume(side),
                "gross_premium": gross,
                "fee_rate": buy_fee if side == "buy" else sell_fee,
                "fee": fee, "signed_cash_flow": cash_flow,
                "slices": [] if role == "maker" else [
                    {"level": level, "price": price_value, "quantity": quantity}
                    for level, price_value, quantity in (slices or [])
                ],
            })
        expiry_profit = entry_cash_flow + terminal_cash_flow if feasible else None
        entry_debit = -entry_cash_flow if feasible and direction == "long" else None
        entry_credit = entry_cash_flow if feasible and direction == "short" else None
        monthly_value = None
        if feasible and days_to_expiry > 0:
            if direction == "long" and entry_debit is not None and entry_debit > 0 and terminal_cash_flow > 0:
                monthly_value = (terminal_cash_flow / entry_debit) ** (30 / days_to_expiry) - 1
            elif direction == "short" and entry_credit is not None and entry_credit > 0:
                liability = -terminal_cash_flow
                if liability > 0:
                    monthly_value = 1 - (liability / entry_credit) ** (30 / days_to_expiry)
        break_even = None
        if feasible:
            fee_rate = buy_fee if maker_side == "buy" else sell_fee
            if maker_side == "buy":
                boundary = (hedge_cash_flow + terminal_cash_flow) / (notional_units * (1 + fee_rate))
                break_even = round_to_tick(boundary, tick_size, "floor")
            else:
                boundary = -(hedge_cash_flow + terminal_cash_flow) / (notional_units * (1 - fee_rate))
                break_even = round_to_tick(boundary, tick_size, "ceil")
        routes.append({
            "maker_leg": maker_leg, "maker_side": maker_side,
            "maker_price": maker_price, "maker_queue_ahead": maker_queue,
            "hedge_capacity_boxes": hedge_capacity, "feasible": feasible,
            "execution_grade": bool(feasible and market_data_valid),
            "entry_cash_flow": entry_cash_flow if feasible else None,
            "entry_debit": entry_debit, "entry_credit": entry_credit,
            "opening_fee": opening_fee if feasible else None,
            "terminal_cash_flow": terminal_cash_flow if feasible else None,
            "settlement_cost": settlement_total if settlement_cost_per_contract is not None else None,
            "expiry_profit": expiry_profit,
            "profit_label": "net_profit" if settlement_cost_per_contract is not None else "pre_settlement_profit",
            "days_to_expiry": days_to_expiry,
            "monthly_metric": "monthly_equivalent_rate",
            "monthly_value": monthly_value,
            "break_even_maker_price": break_even,
            "quality_reasons": list(quality_reasons), "legs": leg_rows,
        })
    routes.sort(key=lambda row: (
        0 if row["execution_grade"] else 1,
        0 if row["feasible"] else 1,
        -(row["expiry_profit"] if row["expiry_profit"] is not None else float("-inf")),
        row["maker_leg"],
    ))
    for rank, route in enumerate(routes, 1):
        route["rank"] = rank
    return routes
