import math
from typing import Any


def run_gold_kalman_filter(
    prices1: list[float],
    prices2: list[float],
    times: list[int],
    delta: float = 1e-4,
    meas_variance: float = 1e-3,
) -> dict[str, Any]:
    """Run online Kalman filter on log prices of two gold ETFs to compute dynamic

    hedge ratio beta(t), latent arbitrage spread e(t), and normalized Z-score
    Z(t).
    """
    n = min(len(prices1), len(prices2), len(times))
    if n == 0:
        return {
            "times": [],
            "beta": [],
            "alpha": [],
            "spread": [],
            "z_score": [],
            "p1_norm": [],
            "p2_norm": [],
        }

    # States: [beta, alpha]^T
    # Initial estimate from initial price ratio if available
    init_p1 = max(prices1[0], 1.0)
    init_p2 = max(prices2[0], 1.0)
    beta = math.log(init_p1) / math.log(init_p2) if init_p2 > 1.0 else 1.0
    alpha = math.log(init_p1) - beta * math.log(init_p2)

    # State covariance matrix R = [[r11, r12], [r21, r22]]
    r11 = 1.0
    r12 = 0.0
    r21 = 0.0
    r22 = 1.0

    # Process noise covariance W
    q1 = delta
    q2 = delta

    out_times: list[int] = []
    out_beta: list[float] = []
    out_alpha: list[float] = []
    out_spread: list[float] = []
    out_z_score: list[float] = []
    out_p1_norm: list[float] = []
    out_p2_norm: list[float] = []

    for i in range(n):
        p1 = prices1[i]
        p2 = prices2[i]
        t = times[i]

        if p1 <= 0 or p2 <= 0:
            continue

        y = math.log(p1)
        x = math.log(p2)

        # 1. State prediction covariance: R = R + W
        r11 += q1
        r22 += q2

        # 2. Measurement prediction: y_hat = beta * x + alpha
        y_hat = beta * x + alpha
        e = y - y_hat

        # 3. Innovation covariance: Q = H R H^T + V
        q = x * x * r11 + 2.0 * x * r12 + r22 + meas_variance
        if q <= 0:
            q = 1e-6

        # 4. Kalman Gain: K = R H^T / Q
        k1 = (r11 * x + r12) / q
        k2 = (r21 * x + r22) / q

        # 5. State update
        beta += k1 * e
        alpha += k2 * e

        # 6. Covariance update: R = (I - K H) R
        hr1 = r11 * x + r12
        hr2 = r12 * x + r22
        r11 -= k1 * hr1
        r12 -= k1 * hr2
        r21 = r12
        r22 -= k2 * hr2

        # 7. Normalized Z-score
        z = e / math.sqrt(q)

        out_times.append(t)
        out_beta.append(round(beta, 5))
        out_alpha.append(round(alpha, 5))
        out_spread.append(round(e, 5))
        out_z_score.append(round(z, 3))
        out_p1_norm.append(round(math.log(p1 / init_p1), 5))
        out_p2_norm.append(round(math.log(p2 / init_p2), 5))

    return {
        "times": out_times,
        "beta": out_beta,
        "alpha": out_alpha,
        "spread": out_spread,
        "z_score": out_z_score,
        "p1_norm": out_p1_norm,
        "p2_norm": out_p2_norm,
    }
