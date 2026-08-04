"""Deterministic option pricing, inversion, parity-forward and ORC Wing primitives."""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import median
from typing import Iterable, Literal, Sequence

import numpy as np
from scipy.optimize import brentq, least_squares
from scipy.special import ndtr

MIN_IV = 0.0005
MAX_IV = 4.0
MODEL_VERSION = "orc-wing-v1"


def black76_price(
    forward: float, strike: float, rate: float, ttm: float, volatility: float,
    option_type: Literal["call", "put"],
) -> float:
    if min(forward, strike, ttm, volatility) <= 0:
        raise ValueError("forward, strike, ttm and volatility must be positive")
    discount = math.exp(-rate * ttm)
    sigma_t = volatility * math.sqrt(ttm)
    d1 = (math.log(forward / strike) + 0.5 * volatility * volatility * ttm) / sigma_t
    d2 = d1 - sigma_t
    if option_type == "call":
        return discount * (forward * ndtr(d1) - strike * ndtr(d2))
    if option_type == "put":
        return discount * (strike * ndtr(-d2) - forward * ndtr(-d1))
    raise ValueError("option_type must be call or put")


def black76_bounds(
    forward: float, strike: float, rate: float, ttm: float,
    option_type: Literal["call", "put"],
) -> tuple[float, float]:
    discount = math.exp(-rate * ttm)
    if option_type == "call":
        return discount * max(forward - strike, 0.0), discount * forward
    if option_type == "put":
        return discount * max(strike - forward, 0.0), discount * strike
    raise ValueError("option_type must be call or put")


def implied_volatility(
    price: float, forward: float, strike: float, rate: float, ttm: float,
    option_type: Literal["call", "put"],
) -> float:
    if price <= 0 or ttm <= 0:
        raise ValueError("price and ttm must be positive")
    lower, upper = black76_bounds(forward, strike, rate, ttm, option_type)
    tolerance = max(1e-10, upper * 1e-12)
    if price < lower - tolerance or price > upper + tolerance:
        raise ValueError("price_outside_no_arbitrage_bounds")
    low_price = black76_price(forward, strike, rate, ttm, MIN_IV, option_type)
    high_price = black76_price(forward, strike, rate, ttm, MAX_IV, option_type)
    if price < low_price - tolerance or price > high_price + tolerance:
        raise ValueError("iv_outside_supported_range")
    return float(brentq(
        lambda sigma: black76_price(forward, strike, rate, ttm, sigma, option_type) - price,
        MIN_IV, MAX_IV, xtol=1e-12, rtol=1e-12, maxiter=200,
    ))


def black76_vega(forward: float, strike: float, rate: float, ttm: float, volatility: float) -> float:
    if min(forward, strike, ttm, volatility) <= 0:
        return 0.0
    d1 = (math.log(forward / strike) + 0.5 * volatility * volatility * ttm) / (volatility * math.sqrt(ttm))
    return math.exp(-rate * ttm) * forward * math.sqrt(ttm) * math.exp(-0.5 * d1 * d1) / math.sqrt(2 * math.pi)


def parity_forward_bounds(
    strike: float, rate: float, ttm: float,
    call_bid: float, call_ask: float, put_bid: float, put_ask: float,
) -> tuple[float, float]:
    growth = math.exp(rate * ttm)
    lower = strike + growth * (call_bid - put_ask)
    upper = strike + growth * (call_ask - put_bid)
    if lower <= 0 or upper <= 0 or lower > upper:
        raise ValueError("invalid_parity_forward_interval")
    return lower, upper


def robust_forward(intervals: Iterable[tuple[float, float, float]]) -> tuple[float, float, float]:
    """Return envelope and weighted median of interval midpoints.

    Each tuple is ``(lower, upper, weight)``. The central estimate remains inside
    the intersection when the intervals overlap, otherwise inside their envelope.
    """
    rows = [(lo, hi, max(float(weight), 1e-12)) for lo, hi, weight in intervals if lo > 0 and hi >= lo]
    if not rows:
        raise ValueError("no_valid_forward_intervals")
    values = sorted(((lo + hi) / 2, weight) for lo, hi, weight in rows)
    cutoff = sum(weight for _, weight in values) / 2
    running = 0.0
    central = values[-1][0]
    for value, weight in values:
        running += weight
        if running >= cutoff:
            central = value
            break
    intersection_low, intersection_high = max(r[0] for r in rows), min(r[1] for r in rows)
    envelope_low, envelope_high = min(r[0] for r in rows), max(r[1] for r in rows)
    if intersection_low <= intersection_high:
        central = min(max(central, intersection_low), intersection_high)
    return envelope_low, envelope_high, min(max(central, envelope_low), envelope_high)


@dataclass(frozen=True)
class WingParameters:
    vc: float
    sc: float
    pc: float
    cc: float
    dc: float
    uc: float
    dsm: float = 0.5
    usm: float = 0.5


def _smooth_value(x: float, cutoff: float, smoothing: float, vc: float, sc: float, curvature: float) -> float:
    """Quadratic transition from the central parabola to a flat outer level."""
    outer = cutoff * (1.0 + smoothing)
    value_at_cutoff = vc + sc * cutoff + curvature * cutoff * cutoff
    slope_at_cutoff = sc + 2.0 * curvature * cutoff
    span = outer - cutoff
    # q'(cutoff)=slope, q'(outer)=0 and q(cutoff)=central parabola.
    return value_at_cutoff + slope_at_cutoff * (
        (x - cutoff) - (x - cutoff) * (x - cutoff) / (2.0 * span)
    )


def orc_wing(x: float, params: WingParameters) -> float:
    """Original six-region Wing curve in converted strike ``ln(K/F)``."""
    p = params
    if not (p.dc < 0 < p.uc and p.dsm > 0 and p.usm > 0):
        raise ValueError("Wing requires dc < 0 < uc and positive smoothing ranges")
    down_outer, up_outer = p.dc * (1 + p.dsm), p.uc * (1 + p.usm)
    if x < down_outer:
        return _smooth_value(down_outer, p.dc, p.dsm, p.vc, p.sc, p.pc)
    if x < p.dc:
        return _smooth_value(x, p.dc, p.dsm, p.vc, p.sc, p.pc)
    if x < 0:
        return p.vc + p.sc * x + p.pc * x * x
    if x < p.uc:
        return p.vc + p.sc * x + p.cc * x * x
    if x < up_outer:
        return _smooth_value(x, p.uc, p.usm, p.vc, p.sc, p.cc)
    return _smooth_value(up_outer, p.uc, p.usm, p.vc, p.sc, p.cc)


def fit_orc_wing(
    log_moneyness: Sequence[float], iv: Sequence[float], weights: Sequence[float] | None = None,
) -> tuple[WingParameters, float, bool]:
    x = np.asarray(log_moneyness, dtype=float)
    y = np.asarray(iv, dtype=float)
    if len(x) < 7 or len(np.unique(x)) < 7 or not np.any(x < 0) or not np.any(x > 0):
        raise ValueError("insufficient_strikes")
    w = np.ones_like(x) if weights is None else np.sqrt(np.clip(np.asarray(weights, dtype=float), 1e-6, 1e6))
    vc0 = float(np.clip(np.median(y[np.argsort(np.abs(x))[: min(3, len(x))]]), MIN_IV, MAX_IV))
    slope0 = float(np.polyfit(x, y, 1)[0]) if len(x) > 1 else 0.0
    dc0 = float(np.clip(np.quantile(x[x < 0], 0.4), -2.0, -1e-3))
    uc0 = float(np.clip(np.quantile(x[x > 0], 0.6), 1e-3, 2.0))

    def unpack(theta: np.ndarray) -> WingParameters:
        return WingParameters(*map(float, theta), dsm=0.5, usm=0.5)

    def residual(theta: np.ndarray) -> np.ndarray:
        p = unpack(theta)
        return np.asarray([(orc_wing(float(z), p) - target) * weight for z, target, weight in zip(x, y, w)])

    result = least_squares(
        residual, np.array([vc0, slope0, 0.1, 0.1, dc0, uc0]),
        bounds=(np.array([MIN_IV, -10, -50, -50, -2, 1e-4]), np.array([MAX_IV, 10, 50, 50, -1e-4, 2])),
        max_nfev=3000, xtol=1e-12, ftol=1e-12, gtol=1e-12,
    )
    params = unpack(result.x)
    rmse = float(math.sqrt(np.average(np.square([orc_wing(float(z), params) - target for z, target in zip(x, y)]), weights=np.square(w))))
    return params, rmse, bool(result.success and np.all(np.isfinite(result.x)))


def point_weight(vega: float, depth: float, quote_age_seconds: float, max_quote_age_seconds: float, penalty: float = 1.0) -> float:
    freshness = max(0.05, 1.0 - quote_age_seconds / max(max_quote_age_seconds, 1.0))
    return float(np.clip(vega, 1e-4, 1e4) * np.clip(math.log1p(max(depth, 0)), 0.1, 20) * freshness * np.clip(penalty, 0.05, 1.0))


def interpolate_parameters(left: WingParameters, right: WingParameters, left_ttm: float, right_ttm: float, target_ttm: float) -> WingParameters:
    if right_ttm <= left_ttm:
        raise ValueError("right_ttm must exceed left_ttm")
    alpha = min(1.0, max(0.0, (target_ttm - left_ttm) / (right_ttm - left_ttm)))
    return WingParameters(**{
        name: getattr(left, name) * (1 - alpha) + getattr(right, name) * alpha
        for name in WingParameters.__dataclass_fields__
    })
