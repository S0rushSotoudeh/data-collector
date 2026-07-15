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
CALCULATION_VERSION = "parity-v3"


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

    Each package pays ``strike`` per underlying share at expiry.  Its capital
    base is the actual opening cash outflow after fees and call-sale proceeds.
    Yields use continuous annual compounding, matching the bond curve.
    """
    if minimum_ytm_spread_bps < 0:
        raise ValueError("minimum YTM spread must not be negative")
    target_ytm = borrowing_rate + minimum_ytm_spread_bps / 10_000.0
    pv_borrowing = present_value(strike, borrowing_rate, ttm_years)
    target_capital = present_value(strike, target_ytm, ttm_years)

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
        expiry_profit = strike - capital
        holding_return = strike / capital - 1 if capital > 0 else None
        ytm = math.log(strike / capital) / ttm_years if capital > 0 and ttm_years > 0 else None
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
            f"{name}_capital_per_share": capital,
            f"{name}_capital_per_contract": capital * multiplier,
            f"{name}_total_capital": capital * package_shares,
            f"{name}_expiry_profit_per_share": expiry_profit,
            f"{name}_expiry_profit_per_contract": expiry_profit * multiplier,
            f"{name}_total_expiry_profit": expiry_profit * package_shares,
            f"{name}_holding_return": holding_return,
            f"{name}_ytm": ytm,
            f"{name}_ytm_spread_bps": ytm_spread_bps,
            f"{name}_opportunity": capital <= target_capital + 1e-12 * max(1.0, abs(target_capital)) and capacity > 0,
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
