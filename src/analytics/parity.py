"""Pure put-call parity calculations.

All monetary values in this module are IRR per underlying share.  Option book
volumes are contracts; stock book volumes are shares.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Literal

from src.analytics.depth import DepthBook

YEAR_SECONDS = 365.25 * 24 * 60 * 60
CALCULATION_VERSION = "parity-v5"


@dataclass(frozen=True)
class Fees:
    stock_buy: float = 0.0
    stock_sell: float = 0.0
    call_buy: float = 0.0
    call_sell: float = 0.0
    put_buy: float = 0.0
    put_sell: float = 0.0


@dataclass(frozen=True)
class Book:
    bid: float
    ask: float
    bid_volume: int
    ask_volume: int


FEE_PRESETS: dict[str, dict[str, float]] = {
    # Effective rates published for ordinary equity/ETF and option trades.
    "tse_stock": {"buy": 0.003712, "sell": 0.0088},
    "ifb_stock": {"buy": 0.003712, "sell": 0.0088},
    "tse_equity_etf": {"buy": 0.00116, "sell": 0.0011875},
    "tse_option": {"buy": 0.001, "sell": 0.001},
    "ifb_option": {"buy": 0.001, "sell": 0.001},
}


def margin_per_share(value: float, unit: str, strike: float, multiplier: int) -> float:
    """Convert a margin representation to IRR per underlying share."""
    if value < 0 or strike <= 0 or multiplier <= 0:
        raise ValueError("margin, strike, and multiplier must be valid positive values")
    units = {
        "per_share": value,
        "per_contract": value / multiplier,
        "percent": strike * value / 100.0,
        "basis_points": strike * value / 10_000.0,
    }
    try:
        return units[unit]
    except KeyError as exc:
        raise ValueError(f"unsupported margin unit: {unit}") from exc


def present_value(strike: float, continuous_rate: float, ttm_years: float) -> float:
    if strike <= 0 or ttm_years < 0 or not math.isfinite(continuous_rate):
        raise ValueError("invalid discounting input")
    return strike * math.exp(-continuous_rate * ttm_years)


def fee(price: float, rate: float) -> float:
    if price < 0 or not 0 <= rate < 1:
        raise ValueError("invalid fee input")
    return price * rate


def executable_capacity(
    call_contracts: int, put_contracts: int, stock_shares: int, multiplier: int
) -> tuple[int, list[str]]:
    if multiplier <= 0:
        raise ValueError("multiplier must be positive")
    capacities = {
        "call": max(0, int(call_contracts)),
        "put": max(0, int(put_contracts)),
        "underlying": max(0, int(stock_shares)) // multiplier,
    }
    capacity = min(capacities.values())
    return capacity, [leg for leg, value in capacities.items() if value == capacity]


def round_to_tick(value: float, tick_size: float, direction: Literal["floor", "ceil"]) -> float:
    if tick_size <= 0:
        raise ValueError("tick size must be positive")
    rounding = ROUND_FLOOR if direction == "floor" else ROUND_CEILING
    ticks = (Decimal(str(value)) / Decimal(str(tick_size))).to_integral_value(rounding=rounding)
    return float(ticks * Decimal(str(tick_size)))


def calculate(
    *, call: Book, put: Book, stock: Book, strike: float, ttm_years: float,
    borrowing_rate: float, fees: Fees, minimum_ytm_spread_bps: float,
    multiplier: int, tick_size: float | None = None,
) -> dict[str, object]:
    """Evaluate fixed-payoff maker openings of short call + long put + stock.

    Each package pays ``strike`` per underlying share at expiry before the
    estimated cost of closing its three legs.  The closing cost uses the
    currently executable opposite quotes, matching the parity-v2 convention.
    Its capital base is the actual opening cash outflow after fees and
    call-sale proceeds.  Yields use continuous annual compounding, matching
    the bond curve.
    """
    if minimum_ytm_spread_bps < 0:
        raise ValueError("minimum YTM spread must not be negative")
    target_ytm = borrowing_rate + minimum_ytm_spread_bps / 10_000.0
    pv_borrowing = present_value(strike, borrowing_rate, ttm_years)
    estimated_closing_fee = (
        fee(call.ask, fees.call_buy)
        + fee(put.bid, fees.put_sell)
        + fee(stock.bid, fees.stock_sell)
    )
    net_expiry_receipt = strike - estimated_closing_fee
    target_capital = (
        net_expiry_receipt * math.exp(-target_ytm * ttm_years)
        if net_expiry_receipt > 0
        else 0.0
    )

    strategies = {
        "make_call_ask": {
            "maker_price": call.ask,
            "call_price": call.ask,
            "put_price": put.ask,
            "stock_price": stock.ask,
            "volumes": (call.ask_volume, put.ask_volume, stock.ask_volume),
            "rounding": "ceil",
        },
        "make_put_bid": {
            "maker_price": put.bid,
            "call_price": call.bid,
            "put_price": put.bid,
            "stock_price": stock.ask,
            "volumes": (call.bid_volume, put.bid_volume, stock.ask_volume),
            "rounding": "floor",
        },
        "make_underlying_bid": {
            "maker_price": stock.bid,
            "call_price": call.bid,
            "put_price": put.ask,
            "stock_price": stock.bid,
            "volumes": (call.bid_volume, put.ask_volume, stock.bid_volume),
            "rounding": "floor",
        },
    }
    result: dict[str, object] = {
        "pv_borrowing": pv_borrowing,
        "target_ytm": target_ytm,
        "target_capital_per_share": target_capital,
    }
    for name, strategy in strategies.items():
        maker_price = float(strategy["maker_price"])
        call_price = float(strategy["call_price"])
        put_price = float(strategy["put_price"])
        stock_price = float(strategy["stock_price"])
        call_volume, put_volume, stock_volume = strategy["volumes"]
        capacity, limiting = executable_capacity(call_volume, put_volume, stock_volume, multiplier)
        stock_cost = stock_price + fee(stock_price, fees.stock_buy)
        put_cost = put_price + fee(put_price, fees.put_buy)
        call_proceeds = call_price - fee(call_price, fees.call_sell)
        opening_fee = (
            fee(stock_price, fees.stock_buy)
            + fee(put_price, fees.put_buy)
            + fee(call_price, fees.call_sell)
        )
        capital = stock_cost + put_cost - call_proceeds
        expiry_profit = net_expiry_receipt - capital
        holding_return = net_expiry_receipt / capital - 1 if capital > 0 and net_expiry_receipt > 0 else None
        ytm = (
            math.log(net_expiry_receipt / capital) / ttm_years
            if capital > 0 and net_expiry_receipt > 0 and ttm_years > 0
            else None
        )
        ytm_spread_bps = (ytm - borrowing_rate) * 10_000 if ytm is not None else None
        if name == "make_call_ask":
            boundary = (stock_cost + put_cost - target_capital) / (1 - fees.call_sell)
        elif name == "make_put_bid":
            boundary = (target_capital - stock_cost + call_proceeds) / (1 + fees.put_buy)
        else:
            boundary = (target_capital - put_cost + call_proceeds) / (1 + fees.stock_buy)
        suggested = round_to_tick(boundary, tick_size, strategy["rounding"]) if tick_size else None
        package_shares = multiplier * capacity
        result.update({
            f"{name}_maker_price": maker_price,
            f"{name}_opening_fee": opening_fee,
            f"{name}_estimated_closing_fee": estimated_closing_fee,
            f"{name}_capital_per_share": capital,
            f"{name}_capital_per_contract": capital * multiplier,
            f"{name}_total_capital": capital * package_shares,
            f"{name}_expiry_profit_per_share": expiry_profit,
            f"{name}_expiry_profit_per_contract": expiry_profit * multiplier,
            f"{name}_total_expiry_profit": expiry_profit * package_shares,
            f"{name}_holding_return": holding_return,
            f"{name}_ytm": ytm,
            f"{name}_ytm_spread_bps": ytm_spread_bps,
            f"{name}_opportunity": (
                net_expiry_receipt > 0
                and capital <= target_capital + 1e-12 * max(1.0, abs(target_capital))
                and capacity > 0
            ),
            f"{name}_capacity": capacity, f"{name}_limiting_legs": limiting,
            f"{name}_target_boundary": boundary,
            f"{name}_suggested_maker_price": suggested if suggested is None or suggested >= 0 else None,
            f"{name}_headroom": (maker_price - boundary if name == "make_call_ask" else boundary - maker_price),
        })
    return result


def validate_book(book: Book, leg: str) -> list[str]:
    reasons: list[str] = []
    if book.bid <= 0 or book.ask <= 0:
        reasons.append(f"{leg}_missing_or_non_positive_side")
    if book.bid > book.ask:
        reasons.append(f"{leg}_crossed_book")
    if book.bid_volume <= 0 or book.ask_volume <= 0:
        reasons.append(f"{leg}_zero_volume")
    return reasons


def calculate_v5(
    *, call: DepthBook, put: DepthBook, stock: DepthBook, strike: float,
    ttm_years: float, borrowing_rate: float, fees: Fees,
    minimum_ytm_spread_bps: float, multiplier: int, target_packages: int,
    settlement_cost_per_contract: float = 0, tick_size: float | None = None,
) -> dict[str, object]:
    """Depth-aware parity-v5 pricing with executable and quoteable signals."""
    if multiplier <= 0 or target_packages <= 0 or strike <= 0:
        raise ValueError("invalid parity-v5 sizing")
    settlement_per_share = settlement_cost_per_contract / multiplier
    terminal = strike - settlement_per_share
    if terminal <= 0:
        raise ValueError("settlement cost consumes the fixed payoff")
    target_ytm = borrowing_rate + minimum_ytm_spread_bps / 10_000
    target_capital = terminal * math.exp(-target_ytm * ttm_years)

    def leg_cost(price: float, side: Literal["buy", "sell"], rate: float) -> tuple[float, float]:
        charge = fee(price, rate)
        return (price + charge if side == "buy" else -price + charge), charge

    call_sell = call.vwap("sell", target_packages)
    put_buy = put.vwap("buy", target_packages)
    stock_buy = stock.vwap("buy", target_packages * multiplier)
    direct_capacity = min(
        call.total_volume("sell"), put.total_volume("buy"), stock.total_volume("buy") // multiplier,
    )
    direct_feasible = all(value is not None for value in (call_sell, put_buy, stock_buy))
    direct_capital = None
    direct_fee = None
    direct_profit = None
    direct_return = None
    direct_ytm = None
    direct_spread = None
    if direct_feasible:
        stock_cost, stock_fee = leg_cost(float(stock_buy), "buy", fees.stock_buy)
        put_cost, put_fee = leg_cost(float(put_buy), "buy", fees.put_buy)
        call_cost, call_fee = leg_cost(float(call_sell), "sell", fees.call_sell)
        direct_capital = stock_cost + put_cost + call_cost
        direct_fee = stock_fee + put_fee + call_fee
        direct_profit = terminal - direct_capital
        if direct_capital > 0 and ttm_years > 0:
            direct_return = terminal / direct_capital - 1
            direct_ytm = math.log(terminal / direct_capital) / ttm_years
            direct_spread = (direct_ytm - borrowing_rate) * 10_000
    result: dict[str, object] = {
        "pv_borrowing": present_value(strike, borrowing_rate, ttm_years),
        "target_ytm": target_ytm, "target_capital_per_share": target_capital,
        "direct_take_capital_per_share": direct_capital,
        "direct_take_capital_per_contract": direct_capital * multiplier if direct_capital is not None else None,
        "direct_take_total_capital": direct_capital * multiplier * target_packages if direct_capital is not None else None,
        "direct_take_opening_fee": direct_fee,
        "direct_take_expiry_profit_per_share": direct_profit,
        "direct_take_expiry_profit_per_contract": direct_profit * multiplier if direct_profit is not None else None,
        "direct_take_total_expiry_profit": direct_profit * multiplier * target_packages if direct_profit is not None else None,
        "direct_take_holding_return": direct_return, "direct_take_ytm": direct_ytm,
        "direct_take_ytm_spread_bps": direct_spread, "direct_take_capacity": direct_capacity,
        "direct_take_opportunity": int(bool(direct_feasible and direct_ytm is not None and direct_spread is not None and direct_spread >= minimum_ytm_spread_bps)),
    }

    strategies = {
        "make_call_ask": ("call", "sell", call.price("buy"), [(put, "buy", fees.put_buy, target_packages), (stock, "buy", fees.stock_buy, target_packages * multiplier)], fees.call_sell),
        "make_put_bid": ("put", "buy", put.price("sell"), [(call, "sell", fees.call_sell, target_packages), (stock, "buy", fees.stock_buy, target_packages * multiplier)], fees.put_buy),
        "make_underlying_bid": ("underlying", "buy", stock.price("sell"), [(call, "sell", fees.call_sell, target_packages), (put, "buy", fees.put_buy, target_packages)], fees.stock_buy),
    }
    for name, (maker_leg, maker_side, current_price, takers, maker_fee_rate) in strategies.items():
        hedge_cost = 0.0
        hedge_fee = 0.0
        capacities: list[int] = []
        hedge_feasible = True
        for book, side, rate, quantity in takers:
            price = book.vwap(side, quantity)
            capacities.append(book.total_volume(side) // (multiplier if book is stock else 1))
            if price is None:
                hedge_feasible = False
                continue
            cost, charge = leg_cost(price, side, rate)
            hedge_cost += cost
            hedge_fee += charge
        capacity = min(capacities)
        if maker_side == "buy":
            boundary = (target_capital - hedge_cost) / (1 + maker_fee_rate)
            rounded = round_to_tick(boundary, tick_size, "floor") if tick_size else boundary
            maker_bid = call.price("sell") if maker_leg == "call" else put.price("sell") if maker_leg == "put" else stock.price("sell")
            maker_ask = call.price("buy") if maker_leg == "call" else put.price("buy") if maker_leg == "put" else stock.price("buy")
            suggested = min(rounded, maker_ask - tick_size) if tick_size and maker_ask is not None else rounded
            quoteable = bool(hedge_feasible and maker_bid is not None and suggested >= maker_bid and suggested > 0)
            headroom = rounded - maker_bid if maker_bid is not None else None
        else:
            boundary = (hedge_cost - target_capital) / (1 - maker_fee_rate)
            rounded = round_to_tick(boundary, tick_size, "ceil") if tick_size else boundary
            maker_bid, maker_ask = call.price("sell"), call.price("buy")
            suggested = max(rounded, maker_bid + tick_size) if tick_size and maker_bid is not None else rounded
            quoteable = bool(hedge_feasible and maker_ask is not None and suggested <= maker_ask and suggested > 0)
            headroom = maker_ask - rounded if maker_ask is not None else None
        capital = None
        opening_fee = hedge_fee
        if current_price is not None:
            maker_cost, maker_charge = leg_cost(current_price, maker_side, maker_fee_rate)
            capital = hedge_cost + maker_cost
            opening_fee += maker_charge
        expiry_profit = terminal - capital if capital is not None else None
        holding_return = terminal / capital - 1 if capital is not None and capital > 0 else None
        ytm = math.log(terminal / capital) / ttm_years if capital is not None and capital > 0 and ttm_years > 0 else None
        spread = (ytm - borrowing_rate) * 10_000 if ytm is not None else None
        maker_book = call if maker_leg == "call" else put if maker_leg == "put" else stock
        result.update({
            f"{name}_maker_price": current_price, f"{name}_opening_fee": opening_fee,
            f"{name}_estimated_closing_fee": settlement_per_share,
            f"{name}_capital_per_share": capital,
            f"{name}_capital_per_contract": capital * multiplier if capital is not None else None,
            f"{name}_total_capital": capital * multiplier * target_packages if capital is not None else None,
            f"{name}_expiry_profit_per_share": expiry_profit,
            f"{name}_expiry_profit_per_contract": expiry_profit * multiplier if expiry_profit is not None else None,
            f"{name}_total_expiry_profit": expiry_profit * multiplier * target_packages if expiry_profit is not None else None,
            f"{name}_holding_return": holding_return, f"{name}_ytm": ytm,
            f"{name}_ytm_spread_bps": spread, f"{name}_opportunity": int(quoteable),
            f"{name}_quoteable": int(quoteable), f"{name}_capacity": capacity,
            f"{name}_limiting_legs": [], f"{name}_target_boundary": boundary,
            f"{name}_suggested_maker_price": suggested, f"{name}_headroom": headroom,
            f"{name}_queue_ahead_volume": maker_book.queue_volume(maker_side),
        })
    return result
