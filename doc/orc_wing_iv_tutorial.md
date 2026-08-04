# ORC Wing fit and implied volatility

This is a short guide to the IV-surface path implemented in
`src/analytics/iv.py` and `src/analytics/iv_engine.py`.

## 1. What the code calculates

The pricing primitive is **Black-76**, so it uses a forward price `F`:

```text
price = Black76(F, K, r, T, sigma, option_type)
```

Here `K` is strike, `r` is the continuously compounded annual rate, `T` is
time to expiry in years, and `sigma` is annual volatility as a decimal. For
example, `0.25` means 25% IV.

The engine obtains `F` from executable put-call-parity intervals. It uses a
bond-curve rate when available and falls back to the configured manual rate.

## 2. From a market price to IV

`implied_volatility()` numerically finds the volatility that reproduces the
observed option price:

```python
from src.analytics.iv import black76_price, implied_volatility

market_price = black76_price(
    forward=100,
    strike=105,
    rate=0.20,
    ttm=0.5,
    volatility=0.37,
    option_type="call",
)

iv = implied_volatility(market_price, 100, 105, 0.20, 0.5, "call")
# iv is approximately 0.37
```

The inversion uses Brent's method. The input must pass the project's checks:

- price and time to expiry must be positive;
- price must be inside the Black-76 no-arbitrage bounds;
- the solution must be inside the supported IV range, `0.0005` to `4.0`.

The engine calculates IV separately for bid and ask prices. At each strike it
keeps the out-of-the-money contract: puts below the forward and calls at or
above the forward. A valid point also receives a weight based on vega, quote
depth, quote freshness, and an optional penalty.

## 3. What the ORC Wing curve is

The curve models IV as a function of log moneyness:

```text
x = ln(K / F)
```

Its six fitted parameters are:

| Parameter | Meaning |
| --- | --- |
| `vc` | central IV at `x = 0` |
| `sc` | central slope |
| `pc` | left/put-side curvature for `x < 0` |
| `cc` | right/call-side curvature for `x > 0` |
| `dc` | negative left transition point |
| `uc` | positive right transition point |

In the central regions the implementation is:

```text
x < 0:  vc + sc*x + pc*x²
x >= 0: vc + sc*x + cc*x²
```

Around `dc` and `uc` the curve transitions smoothly to a flat outer level.
The smoothing ranges are fixed at `dsm = 0.5` and `usm = 0.5`. The function
is continuous at both transition points and at `x = 0`.

Example from the tests:

```python
import math
from src.analytics.iv import WingParameters, orc_wing

params = WingParameters(0.215, -0.0075, 0.015, 0.0075, -0.5, 0.5)
x = math.log(110 / 105)
iv = orc_wing(x, params)
# approximately 0.2147, or 21.47%
```

## 4. Fitting a smile

Build one `x` and one IV value for each valid option point, then fit one wing
per expiry and per quote side:

```python
import math
from src.analytics.iv import fit_orc_wing

x = [math.log(strike / forward) for strike, forward in points]
y = [point_iv for point_iv in iv_points]
params, rmse, converged = fit_orc_wing(x, y, weights)
```

The fit is a bounded weighted least-squares optimization. It needs at least
seven unique strikes, with observations on both sides of `x = 0`. The result
contains the fitted parameters, an RMSE in decimal-IV units, and a convergence
flag. For example, `rmse = 0.001` is about 0.1 IV percentage point.

The API exposes the stored raw points and fits at:

```text
GET /api/v1/iv-surface/runs/{run_id}/points
GET /api/v1/iv-surface/runs/{run_id}/fits
GET /api/v1/iv-surface/runs/{run_id}/grid
```

The grid endpoint evaluates only converged fits over `x` from `-1` to `1`.
Inspect `converged`, `rmse`, `point_count`, and `quality_flags` before using a
fit. One possible warning is `fitted_bid_above_ask`, which means the fitted
bid curve exceeded the fitted ask curve somewhere on the validation grid.

