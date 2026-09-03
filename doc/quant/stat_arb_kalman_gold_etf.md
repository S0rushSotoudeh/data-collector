# Cross-Sectional Mispricing Monitor for Iranian Gold ETFs

## Goal

Estimate relative fair price and mispricing for each gold ETF with a fresh
level-1 book on a one-second decision clock. This is a **market monitor**, not
a pair-trading or entry/exit model. One shared scalar Kalman filter estimates
the common gold factor; scoring excludes the ETF's current update, not its
historical contribution to that factor.

Order books alone identify **relative** mispricing. If every ETF is jointly
mispriced versus gold/NAV, the latent factor moves with them and residuals stay
near zero. Absolute mispricing requires an external observation such as NAV,
gold certificates, a gold future, or another gold/IRR benchmark.

---

## 1. Admin-selected ranges and controls

Each run has three explicit date-and-time selections, displayed in exchange
local time, `Asia/Tehran`. Store timezone-aware instants and interpret every
range as `[From, To)`: include From and exclude To.

| Input | Purpose |
|---|---|
| `training_from`, `training_to` | Learn model parameters |
| `validation_from`, `validation_to` | Assess configuration choices on later data |
| `test_from`, `test_to` | Final unseen evaluation |

Require:

```text
training_from < training_to
training_to <= validation_from < validation_to
validation_to <= test_from < test_to
```

Gaps between ranges are allowed. Report actual coverage, missing periods, and
unusable observations; never silently shorten, extend, or shift a range. A run
cannot produce a calibration or evaluation for which the selected data lacks
the required valid observations. Report that limitation instead of inventing
parameters or results.

The admin also supplies:

| Input | Meaning |
|---|---|
| `kalman_half_life_seconds > 0` | Desired reference memory of the filter |
| `analysis_horizon_seconds > 0` | Future interval used for evaluation |
| `warmup_seconds >= 0` | Time after initialization before publishing scores/alerts |
| `max_quote_age > 0` | Maximum permitted quote age, in seconds |

There is no fixed month limit, training lookback, split percentage, minimum
session count, or automatic daily retraining. Available history constrains the
chosen ranges; it does not prescribe them. Changing calibration or configuration
requires a new run. Lock all choices before examining final test results.

## 2. Level-1 microprice

For ETF `i`:

```text
b_i = best bid price          q_bi = best bid quantity
a_i = best ask price          q_ai = best ask quantity

mid_i       = (a_i + b_i) / 2
spread_i    = a_i - b_i
imbalance_i = (q_bi - q_ai) / (q_bi + q_ai)

microprice_i = (a_i*q_bi + b_i*q_ai) / (q_bi + q_ai)
             = mid_i + spread_i/2 * imbalance_i
```

Use only observations satisfying:

```text
b_i > 0
a_i > b_i
q_bi > 0
q_ai > 0
quote_age_i <= max_quote_age
phase == continuous_trading
```

This is a level-1 quantity-weighted price proxy, not a fitted microprice model.

---

## 3. Train once per run

ETF unit prices differ, so raw prices are not comparable. Define:

```text
y_i,t = log(microprice_i,t)
beta_i = 1
y_i,t = alpha_i + f_t + epsilon_i,t
```

Use only the selected training range. Reconstruct valid books on the decision
grid, with at least three fresh ETFs per retained timestamp. One snapshot per
symbol per second gives time-based sampling rather than overweighting symbols
that emit more changes. Repeated snapshots in these calibration statistics do
not count as independent observations or new Kalman updates.

Estimate one robust log-price offset per ETF, then normalize:

```text
c_t     = median_j(y_j,t) over fresh training ETFs
alpha_i = median_t(y_i,t - c_t)
p_i,t   = y_i,t - alpha_i
p_i,t   = f_t + noise_i,t
```

Estimate noise from normalized residuals against the peer median:

```text
e_i,t = p_i,t - median_j(p_j,t) over fresh j != i
MAD_i = median_t(abs(e_i,t - median_t(e_i,t)))
r_i   = max((1.4826 * MAD_i)^2, 1e-12)
```

`r_i` is a robust residual-noise proxy in normalized log-price variance, not a
guarantee of independent Gaussian measurement errors. The floor is numerical;
it does not make empty or uninformative training data sufficient. Omit symbols
that cannot be calibrated and report why. Freeze eligibility rules and learned
parameters; live freshness and book-validity checks still apply.

Fit `alpha_i` and `r_i` once; derive `q` below. Freeze all three throughout
validation and testing. A new training range means a new run. The historical
offset defines a normal relative basis, not an absolute NAV anchor.

## 4. Calibration history versus filter memory

**Frozen parameters do not mean frozen fair prices.** Each update carries only
the previous factor estimate and uncertainty, `(f, P)`. It does not reread the
training range or recalculate a rolling window of raw ticks.

Derive process variance from the admin's half-life and training-data quality:

```text
R_t       = 1 / sum_i(1/r_i) over new observations in training batch t
R_ref     = median_t(R_t) over nonempty training batches
Delta_ref = median elapsed seconds between nonempty batches within a session
K_ref     = 1 - 2^(-Delta_ref / kalman_half_life_seconds)
q         = R_ref * K_ref^2 / ((1 - K_ref) * Delta_ref)
```

Use the same new-observation rules as runtime. Exclude overnight and missing-data
gaps from interval estimation; require finite positive reference values. This
is the steady-state scalar random-walk relation, not an independent fit of `q`
that can override the admin's chosen memory.

With approximately constant observation quality and intervals, about 95% of
the filter's weight lies within the latest `4.32 * half_life`. For example, a
30-second half-life means approximately 130 seconds of effective history, not
a hard cutoff. Coverage and observation gaps change actual memory. The analysis
horizon is separate: it controls future evaluation, not filter smoothing.

---

## 5. Scalar Kalman consensus

State model:

```text
f_t = f_(t-1) + eta_t       eta_t ~ N(0, q*Delta_t)
p_i,t = f_t + nu_i,t        nu_i,t ~ N(0, r_i)
```

Prediction:

```text
f_minus = f_(t-1)
P_minus = P_(t-1) + q*Delta_t
```

`Delta_t` is elapsed seconds since the preceding decision within the session.
Let `I_t` be all fresh, valid, calibrated ETFs, and `U_t` the subset with a new
level-1 observation retained in this batch. Define `w_i = 1/r_i`. Sum only over
`U_t`, not every cached book:

```text
W = sum_(i in U_t)(w_i)
B = sum_(i in U_t)(w_i*p_i,t)

P_t = 1 / (1/P_minus + W)

f_t = P_t * (f_minus/P_minus + B)
```

Compute scores below before committing this update. If `U_t` is empty, perform
prediction only: no measurement-induced uncertainty reduction. This is one
`O(N)` filter, not a separate filter per ETF pair.

---

## 6. Current-update-only exclusion and mispricing

For each ETF `i` in `I_t`, remove its contribution only if it belongs to `U_t`:

```text
u_i  = w_i if i in U_t, otherwise 0
P_-i = 1 / (1/P_minus + W - u_i)

f_-i = P_-i * (
          f_minus/P_minus
          + B - u_i*p_i,t
       )

delta_i = p_i,t - f_-i
z_i     = delta_i / sqrt(r_i + P_-i)
```

Map the consensus back to ETF `i`'s price scale:

```text
fair_price_i = exp(alpha_i + f_-i)

mispricing_bps_i = 10,000 * (microprice_i/fair_price_i - 1)
```

Interpretation:

```text
z_i > 0  => ETF i is rich relative to the other ETFs
z_i < 0  => ETF i is cheap relative to the other ETFs
|z_i|    => deviation scaled by modeled uncertainty
```

Require at least three fresh ETFs and completed warm-up before publishing a
score. This does not imply that three new observations arrived in this batch.

This is **not full historical leave-one-out**: the shared prior contains older
observations from ETF `i`. For an unchanged cached book, its latest observation
may already be in the prior. Persistent mispricing can therefore influence its
own later benchmark. This accepted simplification avoids maintaining one factor
state per ETF; use separate history-excluding states only if that requirement
changes. `z_i` is a diagnostic score, not a calibrated Gaussian tail probability.

---

## 7. Executable mispricing

Microprice can show a deviation that disappears at bid/ask. Report both sides:

```text
cheap_edge_bps_i = 10,000 * (fair_price_i/a_i - 1)
rich_edge_bps_i  = 10,000 * (b_i/fair_price_i - 1)
```

```text
cheap_edge_bps_i > 0  => ask is below modeled fair value
rich_edge_bps_i  > 0  => bid is above modeled fair value
```

These are monitoring fields, not trade signals. Fees and hedge costs are not
included.

---

## 8. Market-level diagnostics

For each timestamp report:

```text
coverage_t      = number of fresh ETFs
factor_t        = f_t
factor_sigma_t  = sqrt(P_t)
max_abs_z_t     = max_i(abs(z_i))

dispersion_t = sum_(i in I_t)((p_i,t - f_t)^2 / r_i)
```

Large `dispersion_t` means the ETF cross-section does not agree on one common
price. It can indicate mispricing, stale books, a halt, a market-structure
event, or model failure.

Suggested alert condition:

```text
coverage_t >= 3
and abs(z_i) >= z_alert
and condition persists for k consecutive decision intervals
```

Choose `z_alert` and `k` using training/validation diagnostics and lock them
before testing. Reset persistence whenever coverage, freshness, or trading-phase
requirements fail. Report empirical exceedance frequency, persistence, and
subsequent relative-price convergence. Without labeled events or an external
fair-value benchmark, do not call these a true false-alert rate.

---

## 9. Output table

One row per fresh ETF and decision timestamp after warm-up:

| Field | Formula/source |
|---|---|
| `decision_time` | Decision boundary; only information available by this time |
| `symbol` | Instrument ID |
| `microprice` | Level-1 formula |
| `fair_price` | Current-update-excluded Kalman consensus |
| `mispricing_bps` | Microprice versus fair price |
| `z_score` | Residual scaled by modeled uncertainty |
| `cheap_edge_bps` | Fair price versus ask |
| `rich_edge_bps` | Bid versus fair price |
| `spread_bps` | `10,000 * spread/mid` |
| `imbalance` | Level-1 quantity imbalance |
| `quote_age` | Decision time minus quote time |
| `coverage` | Fresh ETF count |

Sort by `mispricing_bps` or `z_score`. Associate results with the run's selected
ranges, timezone, configuration, data/calibration identity, and frozen parameter
values. Pairwise matrices are deferred; derive gaps from normalized prices on
demand if a heatmap is needed.

---

## 10. Causal processing order

1. Reconstruct books using only events available by the decision time. Deduplicate
   events; use source sequence information to reconstruct changes within a
   timestamp. Reject ambiguous ordering rather than inventing intermediate books.
2. At each one-second decision boundary, retain the latest new level-1 state per
   ETF, then check validity. An invalidating change must not revive an earlier
   valid quote. Unchanged cached quotes and deeper-book-only changes are not new
   level-1 measurements. Repeated delivery must not re-assimilate a quote.
3. Predict the shared state; compute scores using the prior plus other new
   observations in the batch; only then update once with `U_t`.
4. Publish eligible ETF scores and market diagnostics. Continue causal state
   updates during warm-up or inadequate scoring coverage, without publishing
   scores or alerts.

At each trading session boundary, clear cached books and filter state. Initialize
from the first batch with at least three valid fresh ETFs: `f = B/W`, `P = 1/W`,
with sums over that initial set. Consume those observations once and publish no
scores for initialization. Start the configured warm-up from that timestamp.
Do not carry overnight quotes or accumulate overnight process variance.

Replay validation and test independently, resetting at each range start as well
as session boundaries. If a selected range begins mid-session, wait for valid
book reconstruction and initialize there; do not silently extend the range to
obtain earlier data. Apply warm-up after each initialization.

## 11. Leakage safeguards

- Split every ETF together by time, never randomly by tick or symbol. Fit
  normalization, noise, and data-driven eligibility rules on training only.
- Freeze parameters throughout validation/testing. Updating `(f, P)` from
  already-arrived evaluation observations is causal filtering, not retraining.
- Never use future quotes to interpolate or backfill missing books. Use forward
  filtering, not a future-informed smoother, for reported scores.
- Separate future outcomes from live features. With `H = analysis_horizon_seconds`,
  retain a label only when `t + H` remains strictly inside the same selected
  evaluation range and trading session. Use the latest valid book available at
  that endpoint, subject to freshness; otherwise mark the label unavailable.
- Evaluate convergence with the run's frozen normalization. Do not recompute
  past scores or labels using later fitted offsets.
- If historical arrival timestamps are unavailable, disclose that exchange-time
  replay cannot establish latency-realistic performance. Ingestion timestamps
  from later backfills are not historical arrival times.
- Validation can inform a new configuration/run. Once final test results influence
  a choice, that period is no longer an unseen test for that choice.

---

## 12. Validation requirements

1. With calibration/configuration fixed, appending future observations cannot
   change already-produced scores; duplicate events cannot reduce uncertainty.
2. Reordering delivery within a timestamp batch does not change reconstructed
   inputs or scores when source ordering is known.
3. Changing an ETF's current price within the same valid update set does not
   change its current benchmark; changing its older observations may do so.
4. Check range boundaries, timezone conversion, gaps, warm-up, stale/invalid
   quotes, insufficient coverage, and labels crossing range/session boundaries.
5. Verify `alpha_i`, `r_i`, and `q` remain unchanged during validation/testing.
6. Compare Kalman fair values with a contemporaneous normalized peer-median
   baseline; compare the quantity-weighted proxy with midpoint at horizon `H`.
7. Report residual centering/stability by symbol, empirical exceedance frequency,
   persistence, and subsequent relative-price convergence. Inspect stale, halted,
   auction, and price-limit periods separately rather than interpreting them as
   ordinary dislocations.
8. Summarize performance and coverage by session. Do not treat millions of
   correlated tick observations as millions of independent tests or claim that
   a short selected history establishes performance across market regimes.

## References

- Sasha Stoikov, [The Micro-Price: A High-Frequency Estimator of Future
  Prices](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2970694).
- R. E. Kalman, [A New Approach to Linear Filtering and Prediction
  Problems](https://doi.org/10.1115/1.3662552).
- E. E. Holmes, [Kalman filtering for maximum likelihood estimation given
  corrupted observations](https://faculty.washington.edu/eeholmes/Files/Intro_to_kalman.pdf)
  (forward recursion and state/parameter distinction).
- Hyndman and Athanasopoulos, [Time series cross-validation](https://otexts.com/fpp3/tscv.html)
  (chronological, past-only evaluation).
