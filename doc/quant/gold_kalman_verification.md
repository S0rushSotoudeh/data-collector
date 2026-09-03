# Gold Kalman verification — 2026-09-04

## Functional verification

- Full repository suite: **473 passed**, one existing TestClient deprecation
  warning, in 33.04 seconds (`docker compose exec -T api python -m pytest src/tests -q`).
- After the final chart-sizing correction: **42 passed** in the numerical and
  chart-template suites.
- PostgreSQL migration `o4i5j6k7l8m9` applied; ClickHouse migration 021 applied;
  `python manage.py clickhouse check` reported all migrations applied.
- Real HTTP multipart import accepted a 360-event fixture and rejected an invalid
  manifest with HTTP 422. Unauthenticated APIs returned HTTP 401.
- Both validation and locked final testing traversed HTTP → Redis/Celery →
  PostgreSQL lifecycle/calibrations → ClickHouse → result APIs.
- Progress was monotonic and reached its declared total. Result keys were unique.
- Injected a failure after 440 score rows were durably written. Celery marked the
  run failed. Replaying the same run completed with 1,320 unique scores, exactly
  matching the original successful reference values. Verification run:
  `8b175e28-11dd-4007-bd75-4dc97363afcd`.
- Desktop/mobile browser checks covered populated rankings, method selection,
  shared charts, and the 390-pixel viewport. No horizontal document overflow
  was observed. The hidden-chart initialization sizing issue was corrected.

Numerical checks cover a hand-calculated scalar update, score-before-update
exclusion, future-prefix invariance, duplicate event invariance, source ordering,
late old observations, invalidation, stale/auction/halted books, quorum loss,
warm-up, mid-session initialization, consistent calibration exclusions, zero
MAD, half-life/process variance, exact fractional horizons, missing original
peers, range boundaries, quantity-only changes, persistent steps, recovery,
overshoot, and common-factor shocks.

## Large synthetic replay

Dataset `44f3a944-8791-4541-9157-826b20590247` contains **2,016,000 events**:
35 synthetic ETFs × 14,400 seconds × four sessions. The data have deterministic
noise, a temporary instrument-specific premium/recovery, and invalid-book
samples. They are explicitly labeled synthetic in the application.

The final repeat reused the immutable dataset; its timings exclude generation
and initial import. The benchmark included both API submission/result checks
and separate worker phase timing. These are local observations with other
processes running, not a dedicated hardware capacity guarantee.

| Measurement | Validation | Final test |
|---|---:|---:|
| Worker wall time | 78.69 s | 96.21 s |
| Calibration including history read/reconstruction | 15.93 s | 13.09 s |
| Evaluation read/reconstruction | 3.93 s | 3.72 s |
| Filtering/scoring, all three methods | 4.02 s | 3.11 s |
| Outcome calculation | 0.20 s | 0.31 s |
| Output persistence | 54.47 s | 75.81 s |
| Peak worker-process RSS | 455.89 MiB | 502.93 MiB |
| Score rows, all three methods | 1,510,908 | 1,510,908 |
| Total score/outcome/market rows | 3,065,016 | 3,065,016 |

Total output: **6,130,032 rows**. Persistence dominates elapsed time.

Validation run: `6c02172a-b07f-46cc-9ea1-08bb351da361`.
Final-test run: `8ee3f336-297d-4606-a440-cf99b012243b`.

Raw report: `src/tests/artifacts/gold_consensus_performance.json`.

## API and export performance on the large run

Twenty-four requests, four concurrent clients/tasks, eight observations per
endpoint. The reported p95 uses the nearest-rank method, which equals the
maximum with this small sample; it is not a robust tail-latency estimate.

| Endpoint | Median | Sample p95 |
|---|---:|---:|
| Timeline, 2,000 timestamps | 406 ms | 2,858 ms |
| Instrument history, 2,000 rows | 478 ms | 2,873 ms |
| Snapshot, 35 ETFs | 485 ms | 2,841 ms |

A complete scheduled-method score export streamed **503,636 data rows**,
**183,295,446 bytes**, in **16.30 seconds**. The consumer counted bytes/lines
without materializing the file. The server uses ClickHouse row-block streaming.

Raw report: `src/tests/artifacts/gold_consensus_api_performance.json`.

## Real-data audit and limits

The local database initially contained 16,996,061 stock order-book rows and 35
instruments currently marked gold ETFs. The audit read **1,278,849 actual
level-1 rows** selected using those current flags, checked price/quantity
validity, and found **19,748 invalid books**. The final read/check took 4.01 s.

This audit does not certify historical ETF membership, trading phases, source
ordering before ClickHouse replacement, or historical arrival times. Those
inputs are required before making real-market model-performance claims. The
large benchmark validates implementation and throughput on a known synthetic
event stream; it does not establish profitable signals or out-of-sample market
performance. Real regime/sensitivity studies remain an operator research step.

See `gold_kalman_implementation.md` for input provenance, import format, run
controls, deployment, and reproducible verification commands.
