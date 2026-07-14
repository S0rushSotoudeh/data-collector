"""Pure put-call parity calculations.

All monetary values in this module are IRR per underlying share.  Option book
volumes are contracts; stock book volumes are shares.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Literal

YEAR_SECONDS = 365.25 * 24 * 60 * 60
CALCULATION_VERSION = "parity-v2"


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
    borrowing_rate: float, fees: Fees, required_margin: float,
    multiplier: int, tick_size: float | None = None,
) -> dict[str, object]:
    """Evaluate maker-first openings of short call + long put + long stock.

    The stock is never sold while opening.  Closing costs are estimates only,
    based on the currently executable opposite quotes.
    """
    pv_borrowing = present_value(strike, borrowing_rate, ttm_years)
    closing_fee = fee(call.ask, fees.call_buy) + fee(put.bid, fees.put_sell) + fee(stock.bid, fees.stock_sell)

    strategies = {
        "make_call_ask": (call.ask, call.ask, call.ask_volume, put.ask_volume, stock.ask_volume,
            call.ask + pv_borrowing - put.ask - stock.ask,
            fee(call.ask, fees.call_sell) + fee(put.ask, fees.put_buy) + fee(stock.ask, fees.stock_buy),
            "ceil"),
        "make_put_bid": (put.bid, put.bid, call.bid_volume, put.bid_volume, stock.ask_volume,
            call.bid + pv_borrowing - put.bid - stock.ask,
            fee(call.bid, fees.call_sell) + fee(put.bid, fees.put_buy) + fee(stock.ask, fees.stock_buy),
            "floor"),
        "make_underlying_bid": (stock.bid, stock.bid, call.bid_volume, put.ask_volume, stock.bid_volume,
            call.bid + pv_borrowing - put.ask - stock.bid,
            fee(call.bid, fees.call_sell) + fee(put.ask, fees.put_buy) + fee(stock.bid, fees.stock_buy),
            "floor"),
    }
    result: dict[str, object] = {"pv_borrowing": pv_borrowing}
    for name, (maker_price, _, call_volume, put_volume, stock_volume, gross, opening_fee, rounding) in strategies.items():
        capacity, limiting = executable_capacity(call_volume, put_volume, stock_volume, multiplier)
        net = gross - opening_fee - closing_fee
        surplus = net - required_margin
        if name == "make_call_ask":
            boundary = (put.ask + stock.ask - pv_borrowing + fee(put.ask, fees.put_buy)
                        + fee(stock.ask, fees.stock_buy) + fee(put.bid, fees.put_sell)
                        + fee(stock.bid, fees.stock_sell) + required_margin) / (1 - fees.call_sell - fees.call_buy)
        elif name == "make_put_bid":
            boundary = (call.bid + pv_borrowing - stock.ask - fee(call.bid, fees.call_sell)
                        - fee(stock.ask, fees.stock_buy) - closing_fee - required_margin) / (1 + fees.put_buy)
        else:
            boundary = (call.bid + pv_borrowing - put.ask - fee(call.bid, fees.call_sell)
                        - fee(put.ask, fees.put_buy) - closing_fee - required_margin) / (1 + fees.stock_buy)
        suggested = round_to_tick(boundary, tick_size, rounding) if tick_size else None
        result.update({
            f"{name}_maker_price": maker_price, f"{name}_gross_edge": gross,
            f"{name}_opening_fee": opening_fee, f"{name}_estimated_closing_fee": closing_fee,
            f"{name}_net_edge": net, f"{name}_surplus_edge": surplus,
            f"{name}_gross_edge_per_contract": gross * multiplier,
            f"{name}_net_edge_per_contract": net * multiplier,
            f"{name}_surplus_edge_per_contract": surplus * multiplier,
            f"{name}_opportunity": surplus > 0 and capacity > 0,
            f"{name}_capacity": capacity, f"{name}_limiting_legs": limiting,
            f"{name}_total_value": surplus * multiplier * capacity,
            f"{name}_profitable_boundary": boundary,
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
