import math

import numpy as np
from scipy.optimize import least_squares

FACE_VALUE = 1_000_000


def ns_yield(t: float, b0: float, b1: float, b2: float, lam: float) -> float:
    if t <= 0:
        return b0 + b1
    x = t / lam
    exp_neg_x = math.exp(-x)
    factor = (1 - exp_neg_x) / x
    return b0 + b1 * factor + b2 * (factor - exp_neg_x)


def yield_from_price(
    price_irr: int, face: int = FACE_VALUE, ttm_years: float = 1.0
) -> float:
    if price_irr <= 0 or ttm_years <= 0:
        return float("nan")
    return math.log(face / price_irr) / ttm_years


def fit_nelson_siegel(
    yields: list[float], ttms: list[float]
) -> dict:
    y_arr = np.array(yields, dtype=np.float64)
    t_arr = np.array(ttms, dtype=np.float64)

    if len(y_arr) < 4:
        return _failed_fit("Need at least 4 bonds")

    def residuals(params: np.ndarray) -> np.ndarray:
        b0, b1, b2, lam = params
        x = t_arr / lam
        exp_neg_x = np.exp(-x)
        factor = np.where(t_arr <= 0, 1.0, (1 - exp_neg_x) / x)
        fitted = b0 + b1 * factor + b2 * (factor - exp_neg_x)
        return fitted - y_arr

    p0 = [float(np.mean(y_arr)), 0.0, 0.0, 2.0]
    bounds = ([0.0, -1.0, -1.0, 0.01], [1.0, 1.0, 1.0, 10.0])

    result = least_squares(residuals, p0, bounds=bounds, method="trf")

    if not result.success:
        return _failed_fit(result.message)

    b0, b1, b2, lam = result.x
    x = t_arr / lam
    exp_neg_x = np.exp(-x)
    factor = np.where(t_arr <= 0, 1.0, (1 - exp_neg_x) / x)
    fitted = b0 + b1 * factor + b2 * (factor - exp_neg_x)
    rmse = float(np.sqrt(np.mean((fitted - y_arr) ** 2)))

    return {
        "beta0": float(b0),
        "beta1": float(b1),
        "beta2": float(b2),
        "lambda": float(lam),
        "rmse": rmse,
        "converged": 1,
        "error_message": "",
    }


def _failed_fit(message: str) -> dict:
    return {
        "beta0": None,
        "beta1": None,
        "beta2": None,
        "lambda": None,
        "rmse": None,
        "converged": 0,
        "error_message": str(message),
    }


def classify_signal(spread_bps: float, threshold_bps: float = 50.0) -> str:
    if spread_bps > threshold_bps:
        return "cheap"
    if spread_bps < -threshold_bps:
        return "rich"
    return "fair"
