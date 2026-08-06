# Log moneyness

## Definition

In this project, log moneyness is:

```text
x = ln(K / F)
```

`K` is the option strike and `F` is the forward price for the same expiry and
snapshot. It is **not** `ln(K / S)`; the implementation uses the parity-derived
forward, because the IV calculation is Black-76.

Recovering the strike from `x` is straightforward:

```text
K = F * exp(x)
```

## Reading the sign

| Value of `x` | Meaning |
| --- | --- |
| `x = 0` | strike equals the forward; ATM-forward |
| `x < 0` | strike is below the forward |
| `x > 0` | strike is above the forward |

For example, with `F = 105` and `K = 110`:

```text
x = ln(110 / 105) = 0.04652
```

The strike is about 4.76% above the forward. Conversely, `x = 0.05` means
`K/F = exp(0.05) = 1.0513`, or about 5.13% above the forward. `x = -0.05`
means `K/F = 0.9512`, or about 4.88% below it.

## How the code uses it

The IV engine computes it when fitting each expiry and quote side:

```python
import math

log_moneyness = math.log(strike / forward)
```

The same coordinate is used by the ORC Wing curve and by the IV-surface API.
The grid endpoint returns `log_moneyness` values from `-1` to `1`, together
with DTE and fitted IV. The admin chart labels this axis `log(K/F)`.

Because the forward can change by snapshot and expiry, recompute `x` with the
forward stored on that IV point or fit. Do not reuse a spot price or a forward
from a different expiry.

## A common sign mistake

Black-76's `d1` formula contains `ln(F / K)`, while the ORC Wing coordinate is
`ln(K / F)`. They are negatives of each other:

```text
ln(K / F) = -ln(F / K)
```

Use `ln(K/F)` for Wing parameters and surface plots. Swapping the ratio will
reverse the put-side and call-side directions of the fitted smile.

