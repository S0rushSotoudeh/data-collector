# Cross-Sectional Mispricing Monitor for Iranian Gold ETFs

## Goal

This proposed **market monitor** estimates relative fair price and mispricing
for gold ETFs from fresh level-1 books on a one-second decision clock. One
shared scalar Kalman filter tracks the common gold factor, with parameters
calibrated before each session. It does not define pair trades or entry/exit
rules and is not yet implemented.

Order books alone identify **relative** mispricing. If every ETF is jointly
mispriced versus gold/NAV, the latent factor moves with them and residuals stay
near zero. Absolute mispricing requires an external observation such as NAV,
gold certificates, a gold future, or another gold/IRR benchmark.

---

## 1. Admin-selected history, evaluation ranges, and controls

Display date-and-time selections in `Asia/Tehran`, store timezone-aware
instants, and interpret ranges as `[From, To)`.

| Input | Purpose |
|---|---|
| `history_from` | Earliest history authorized for calibration |
| `validation_from`, `validation_to` | Chronological development evaluation |
| `test_from`, `test_to` | Final evaluation after locking the policy |

Require:

```text
history_from < validation_from < validation_to
validation_to <= test_from < test_to
```

History in `[history_from, test_to)` is authorized for past-only
calibration, including gaps between evaluation ranges. Publish evaluation
scores only inside the selected validation and test ranges. At any decision,
future portions of that authorized history remain unavailable to the model.
Never silently extend history or shift an evaluation range.

| Input | Meaning |
|---|---|
| `symbols` | Admin-selected candidate ETF universe; membership must be valid at the historical time |
| `calibration_lookback_sessions >= 1` | Number of immediately preceding completed exchange sessions used for calibration |
| `min_calibration_observations >= 3` | Minimum distinct valid level-1 observations retained on the decision grid per ETF with at least two fresh peers |
| `kalman_half_life_seconds > 0` | Desired reference memory of the common factor |
| `warmup_seconds >= 0` | Time after state initialization before publishing scores/alerts |
| `analysis_horizon_seconds > 0` | Future interval used for evaluation |
| `max_quote_age > 0` | Maximum permitted quote age, in seconds |
| `z_alert > 0`, integer `k >= 1` | Alert threshold and consecutive qualifying decision count |

Recalibration occurs once per exchange session. The lookback is an integer
number of completed trading sessions, not calendar days or raw ticks. Holidays
do not count as sessions; a scheduled session with missing data does count and
must be reported as missing. Do not silently replace it with an older session.
The requested window must lie entirely on or after `history_from`.

Choose all controls on development data and lock the complete policy before
final testing. The observation minimum is a sufficiency gate, not proof of
statistical reliability. Scheduled parameter changes remain within the same
run; manual changes to controls, symbol selection, or update rules require a
new run.

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
0 <= quote_age_i <= max_quote_age
phase == continuous_trading
```

This is a level-1 quantity-weighted price proxy, not a fitted microprice model.

---

## 3. Calibrate before each session; freeze within the session

For a session opening at `s`, select the configured number of immediately
preceding completed sessions. Use only observations available before `s`.
Exclude the current session, even when an evaluation range starts mid-session.

Calibration produces a version containing its cutoff, selected history,
eligible symbols, `alpha_i`, `r_i`, and `q`. Activate it before initializing the
session's filter. If calibration is delayed, withhold scores until it is ready
and the subsequent warm-up completes. Do not repair a failed calibration using
current-session observations or silently carry an older version forward.

Normalize differing ETF unit prices with a log-price offset:

```text
y_i,t = log(microprice_i,t)
beta_i = 1
y_i,t = alpha_i + f_t + epsilon_i,t
```

Reconstruct valid books on the one-second decision grid over the calibration
window, with at least three fresh ETFs per retained timestamp. Use only the
final eligible symbol set in the following medians. An ETF needs the configured
number of distinct valid level-1 observations with at least two fresh eligible
peers. Omit unsupported symbols and report the reason; if fewer than three
remain, calibration is unavailable for that session.

One snapshot per symbol per second gives time-based sampling rather than
overweighting symbols that emit more changes. Repeated cached snapshots may
contribute to time-weighted calibration statistics, but do not satisfy the
distinct-observation minimum or count as new Kalman measurements. Report both
time coverage and distinct-observation counts. Session eligibility follows
the locked past-only policy.

Estimate one robust log-price offset per ETF, then normalize:

```text
c_t     = median_j(y_j,t) over fresh eligible calibration ETFs
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

Require finite offsets and finite, positive unfloored residual scales. A zero
MAD or insufficient observations makes that ETF's calibration unavailable;
the numerical variance floor cannot manufacture information. Determine the
eligible set and its estimates consistently after exclusions, retaining at
least three ETFs and the required peer support.

`r_i` is a robust residual-noise proxy in normalized log-price variance, not a
guarantee of independent Gaussian measurement errors. The historical offset
defines a normal relative basis, not an absolute NAV anchor. Changing peer
availability can affect this basis; retain coverage diagnostics with each fit.

Derive `q` in section 4, then hold `alpha_i`, `r_i`, and `q` fixed until the next
session. Refitting can absorb a persistent premium or lower z-scores without
price recovery, even at session boundaries. Reset the factor when calibration
changes because new offsets change its coordinate system.

## 4. Calibration history versus filter memory

Each filter update carries only the previous factor estimate and uncertainty,
`(f, P)`. Its memory decays recursively; do not replay a rolling window of ticks.

At each calibration, derive process variance from the admin's half-life and
that calibration window's observation quality:

```text
R_t       = 1 / sum_i(1/r_i) over new eligible observations in calibration batch t
R_ref     = median_t(R_t) over nonempty calibration batches
Delta_ref = median elapsed seconds between nonempty batches within a session
K_ref     = 1 - 2^(-Delta_ref / kalman_half_life_seconds)
q         = R_ref * K_ref^2 / ((1 - K_ref) * Delta_ref)
```

Use the same new-observation rules as runtime. Exclude overnight and missing-data
gaps from interval estimation; require finite positive reference values. This
is the steady-state scalar random-walk relation linking `q` to the chosen memory.

With approximately constant observation quality and intervals, about 95% of
the filter's weight lies within the latest `4.32 * half_life`; coverage and gaps
change actual memory. This is neither a hard cutoff nor an estimate of
mispricing mean-reversion time. Calibration history estimates slower
relationships, warm-up reduces initialization influence, and the analysis
horizon controls future evaluation.

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
prediction only: no measurement-induced uncertainty reduction.

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
own later benchmark. `z_i` is a diagnostic score, not a calibrated Gaussian tail
probability.

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

Edges exclude fees and hedge costs.

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

Reset persistence whenever coverage, freshness, or trading-phase requirements
fail, and at every state initialization or calibration change. A score jump
across sessions may reflect a new reference basis rather than price convergence.
Report empirical exceedance frequency and persistence; without labeled events
or an external fair-value benchmark, these do not establish a false-alert rate.

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
| `calibration_id` | Parameter version used for this score |

Sort by `mispricing_bps` or `z_score`. Associate results with the run's history
and evaluation ranges, timezone, locked policy, candidate universe, and data
identity. Each calibration version stores its cutoff, effective time, selected
sessions, coverage, exclusions, and parameter values. Never overwrite past
scores with later calibrations. Keep future-outcome records separate from live
scores.

---

## 10. Causal processing order

1. Reconstruct books using only events available by the decision time. Deduplicate
   events; use source sequence information to reconstruct changes within a
   timestamp. Reject ambiguous ordering rather than inventing intermediate books.
2. At each one-second decision boundary, retain the latest new level-1 state per
   ETF, then check validity. An invalidating change must not revive an earlier
   valid quote. Unchanged cached quotes and deeper-book-only changes are not new
   level-1 measurements. Repeated delivery must not re-assimilate a quote.
3. Use the active session calibration for the entire batch. Predict the shared
   state; compute scores using the prior plus other new observations in the
   batch; only then update once with `U_t`.
4. Publish eligible ETF scores and market diagnostics. Continue causal state
   updates during warm-up or inadequate scoring coverage, without publishing
   scores or alerts.

At each trading session boundary, activate the new past-only calibration and
clear cached books, filter state, and alert persistence. Initialize from the
first batch with at least three valid fresh calibrated ETFs: `f = B/W`,
`P = 1/W`, with sums over that initial set. Consume those observations once and
publish no scores for initialization. Start the configured warm-up from that
timestamp. Do not carry overnight quotes or accumulate overnight process
variance.

Replay validation and test independently, resetting at each range start as well
as session boundaries. If a selected range begins mid-session, use its session's
past-only calibration, but reconstruct the scoring books and initialize within
the selected range. Do not extend the score replay to obtain earlier filter
state. Apply warm-up after each initialization.

## 11. Chronological evaluation and leakage safeguards

Compare a small number of policies on chronological validation blocks, then
reserve the final test range for the selected policy. Scheduled calibration
continues under the rules in section 3, so earlier test-session prices may
inform later sessions. If test results influence a manual policy choice, that
range becomes development data and final evaluation requires a later unseen
range. Report limited history rather than claiming coverage of unobserved regimes.

### Price-based outcomes that recalibration cannot manufacture

At a published score at time `t`, retain the initial score, fair price, and
the fresh calibrated peer set `J_i,t = I_t excluding i`. Assign equal weights
`v_j = 1 / len(J_i,t)` and freeze those peers and weights for this outcome.
Use midpoint returns to avoid interpreting quantity-only microprice changes
as price convergence:

```text
H = analysis_horizon_seconds

relative_return_i = log(mid_i,t+H / mid_i,t)
                    - sum_(j in J_i,t)(v_j * log(mid_j,t+H / mid_j,t))

directional_recovery_log_bps_i = -sign(delta_i,t) * 10,000 * relative_return_i

initial_mid_gap_i = log(mid_i,t / fair_price_i,t)
anchored_mid_gap_i,H = initial_mid_gap_i + relative_return_i

gap_reduction_log_bps_i = 10,000 * (
    abs(initial_mid_gap_i) - abs(anchored_mid_gap_i,H)
)
```

Positive directional recovery means movement in the original score's suggested
direction; positive gap reduction means the absolute gap narrowed against the
initial fair price advanced by fixed peers' returns. Overshoot can make the
first positive and the second negative. These relative-price diagnostics use
no later fitted parameters and do not measure realized profits. Their log-bps
units differ from the simple percentage bps used for displayed mispricing and
bid/ask edges.

Retain an outcome only if `t + H` is strictly inside the same selected evaluation
range and trading session. At that endpoint, reconstruct the latest available
book for the ETF and every original peer, then validate each book and its
freshness using the reconstruction rules in section 10.
If any required book is unavailable or invalid, mark the
outcome unavailable; do not replace peers, renormalize weights, or interpolate
from future observations. Report missing-outcome rates alongside results.

### Baselines and safeguards

- Compare with a frozen-calibration reference: fit once from the completed
  sessions preceding the first validation session, then reuse that version
  throughout validation and test. Reset its state and apply the same warm-up
  rules. Refit this initial reference independently for separate development
  folds. Report differences in eligibility and coverage, and compare results
  on common valid timestamps as well as each policy's full output.
- Compare with a contemporaneous normalized peer-median fair price using the
  same session calibration. This checks whether Kalman filtering adds value.
  Separately compare the quantity-weighted price proxy with midpoint against
  future midpoint at horizon `H`.
- Split every ETF together by time, never randomly by tick or symbol. Use
  historical eligibility information; do not select past members by later
  survival, liquidity, or performance.
- A bucket's final quote is available at its actual arrival or bucket
  completion, not its start. Never backfill books from future quotes or revise
  reported scores with a future-informed smoother.
- Calibration consumes past price observations, not future recovery labels.
  Any label used to select settings must have matured before the selection
  cutoff. Exclude development observations whose outcome crosses that cutoff.
  Overlapping lookback windows are legitimate; overlapping outcome horizons
  still make observations statistically dependent.
- If original arrival timestamps are unavailable, disclose that exchange-time
  replay cannot establish latency-realistic performance. Ingestion timestamps
  from later backfills are not historical arrival times.

---

## 12. Validation requirements

1. With the policy and historical input prefix fixed, appending future
   observations cannot change earlier calibrations or scores. Changing later
   sessions cannot change an earlier session's outputs. Duplicate events
   cannot reduce uncertainty.
2. Reordering delivery within a timestamp batch does not change reconstructed
   inputs or scores when source ordering is known.
3. Changing an ETF's current price within the same valid update set does not
   change its current benchmark; changing its older observations may do so.
4. Check range boundaries, timezone conversion, gaps, warm-up, stale/invalid
   quotes, insufficient coverage, and labels crossing range/session boundaries.
5. Verify every calibration uses only its declared completed-session window
   before its cutoff, and that `alpha_i`, `r_i`, and `q` stay unchanged within
   the session. Check missing sessions, unsupported symbols, failed calibration,
   delayed activation, mid-session range starts, and parameter-version storage.
6. Check a persistent relative price step and a genuine relative recovery.
   Recalibration may shrink later scores after the step, but cannot change
   stored price-based outcomes or manufacture recovery. Check common factor
   shocks separately from ETF-specific deviations.
7. Compare the scheduled policy, frozen reference, and peer-median baseline
   using section 11. Report directional recovery, gap reduction, overshoot,
   residual stability by symbol, exceedance frequency, and persistence. Smaller
   residuals or fewer alerts alone do not establish a better model.
8. Report coverage, quote age, missing outcomes, initialization loss, and
   calibration changes by session. Inspect stale, halted, auction, and
   price-limit periods separately. Summarize results and uncertainty at session
   or longer block level; millions of correlated seconds are not millions of
   independent tests.
9. Compare sensitivity to lookback, factor half-life, and freshness settings on
   development data, including the effects of correlated peer errors, changing
   basket composition, and parameter uncertainty.

## 13. Compute and scope

For `N` ETFs and `T` decision timestamps, the shared filtering and scoring pass
is `O(N*T)` and carries one scalar factor state plus per-ETF books and parameters.
Read ordered inputs in batches and consume them once.

Calibration runs once per session. If its window contains `L` one-second rows
per ETF, it processes approximately `N*L` values per statistical pass, with
additional work for the medians. A direct array implementation needs `O(N*L)`
working memory. Outputs can contain up to `N*T` rows; reading, reconstruction,
and persistence must be included when measuring total runtime.

Measure event reconstruction, calibration, filtering, outcome calculation, and
persistence separately on a representative replay before estimating runtime.

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
- River, [Progressive validation](https://riverml.xyz/dev/api/evaluate/progressive-val-score/)
  (predict before learning; reveal outcomes only when available).
