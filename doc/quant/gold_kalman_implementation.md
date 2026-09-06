# Gold Kalman monitor: implementation and operation

The monitor implements the scalar cross-sectional model in
`stat_arb_kalman_gold_etf.md`. Open **Gold Analytics → Gold Kalman Monitor**
(`/admin/gold-kalman`). Gold Kalman Runs links each saved policy back to its
monitor. The older two-instrument hedge-ratio function remains separate.

## Input contract

Import an immutable event CSV together with a JSON session/source manifest.
Imports are available only after all rows and event identities pass validation.
A failed import stays unavailable, with an error in dataset metadata. There is
no endpoint to edit an imported dataset. Corrections require a new dataset.

The existing `stock_order_book` is **not automatically treated as a causal event
archive**. Its replacement key omits source sequence, its timestamps have
second resolution, and historical phase/eligibility and arrival timestamps are
not established by the stored rows. Current instrument flags alone cannot
establish historical universe membership. Do not relabel backfill ingestion
times as historical arrival times.

CSV header, in order:

```csv
symbol,available_at,quote_time,sequence,bid,ask,bid_qty,ask_qty,phase
ETF_A,2026-08-01T12:00:01+03:30,2026-08-01T12:00:00+03:30,1,100000,100100,500,400,continuous
```

Prices are IRR. Quantities and invalid/zero books must be retained. Allowed
phases are `continuous`, `auction`, `halted`, and `unknown`. Unknown phases do
not generate scores. Times must include an offset. `available_at` is when an
observation is usable: actual historical arrival time, or the correctly
declared exchange/bucket-completion time. Never date a bucket's last observation
at its beginning. Source sequence disambiguates simultaneous changes. Exact
retransmissions are ignored; conflicting identities are rejected, and late
older source states cannot revive an invalidated book.

Manifest structure:

```json
{
  "name": "Verified gold ETF observations",
  "source_reference": "Source archive identifier and ordering convention",
  "calendar_reference": "Versioned historical exchange calendar source",
  "eligibility_reference": "Historical ETF membership source/version",
  "phase_reference": "Historical instrument phase source/version",
  "clock": "exchange_time",
  "price_unit": "IRR",
  "sessions": [
    {
      "open": "2026-08-01T12:00:00+03:30",
      "close": "2026-08-01T16:00:00+03:30",
      "eligible_symbols": ["ETF_A", "ETF_B", "ETF_C"]
    }
  ]
}
```

The example illustrates structure, not a verified historical calendar. Supply
every actual scheduled session needed for the run, including sessions with no
observations. Do not list holidays as trading sessions. The manifest must cover
history through the test range. `clock` is `historical_arrival`, `exchange_time`,
or `synthetic`; provenance is retained in metadata and run results. Structural
validation does not certify the truth of an operator's source declaration.

## Run workflow

1. Manage immutable observations through the authenticated dataset ingestion API
   (`POST /api/v1/gold-kalman/datasets` with multipart manifest and events files).
   Import controls are intentionally absent from the monitor. Existing snapshots remain available.
2. Select at least three ETF symbols and history, validation, and
   final test bounds. All selections display Tehran local time and use `[from,to)`.
3. Select calibration sessions, minimum distinct observations, factor half-life,
   warm-up, quote freshness, horizon, and alert threshold/persistence.
4. Run **Development validation**. Calibration consumes completed past sessions;
   future portions of the imported dataset are not consulted for filtering.
5. Compare a small number of policies using validation results. Select **Final
   test** from a completed usable validation. The server requires the same
   dataset, controls, universe, and ranges. Changing them requires new validation.
6. Review three methods: session-calibrated Kalman, frozen calibration, and
   contemporaneous normalized peer median. Both Kalman variants reset at session
   and evaluation-range boundaries. No filter state is borrowed from before a
   mid-session range start.

Calibration records retain cutoffs, selected and missing sessions, exclusions,
offsets, observation variances, process variance, distinct counts, and time
coverage. Calibration failures suppress that session; the scheduled method does
not silently reuse yesterday's parameters. For reference-interval estimation,
loss of three-book coverage breaks a missing-data gap; overnight intervals are
always excluded. Initialization consumes the first qualifying batch once and
does not publish a score, including when warm-up is zero.

Outcomes freeze the original fresh peer set and equal weights. The market table
stores that set and its initial midpoints once per method/timestamp; the focal
ETF is excluded to obtain its original peers. Endpoint books come from the
immutable input dataset at exactly `t + horizon`. If a peer is missing, invalid,
or stale, the outcome is unavailable. Endpoints at or beyond a range/session
end are unavailable. Later calibration never enters the outcome formula.

## Persistence and operation

- PostgreSQL: `operation_runs`, `gold_kalman_datasets`, and
  `gold_kalman_calibrations`.
- ClickHouse: `gold_kalman_inputs`, `gold_kalman_scores`,
  `gold_kalman_market`, and `gold_kalman_outcomes`.
- Task: `src.tasks.run_gold_kalman`; family `gold_kalman`; type
  `gold_kalman.replay`. No Beat schedule or order execution is installed.
- Progress counts the frozen reference calibration, each selected session's
  calibration, and each method's decision timestamps. Counts advance after
  corresponding outputs are committed.
- PostgreSQL advisory locking serializes duplicate task delivery. Deterministic
  calibration IDs and ClickHouse replacement keys make repeated writes visible
  once through `FINAL`. Dataset/policy identity must remain unchanged.
- Output storage partitions by decision month. Inputs have no automatic expiry;
  removing them would remove exact replay capability.

All API endpoints require admin authentication and enforce run family. The
run-scoped prefix is `/api/v1/gold-kalman/runs/{run_id}` with `/timeline`,
`/snapshot`, `/history`, `/calibrations`, `/evaluation`, and `/export.csv`.
Timeline and history are paginated. Exports stream blocks and include the run's
policy and source checksum in a leading metadata comment. `kind=outcomes` and
`kind=market` export the separate datasets.

## Deployment and verification

Rebuild API and worker images so both receive the Alembic migration, then apply:

```sh
docker compose exec api alembic upgrade head
docker compose exec api python manage.py clickhouse migrate
docker compose exec api python manage.py clickhouse check
docker compose exec api python -m pytest src/tests -q
```

The PostgreSQL revision is `o4i5j6k7l8m9`. The ClickHouse migration is
`021_gold_consensus.py`: versions 019 and 020 already existed in the inspected
database outside this checkout and must not be reused.

The opt-in benchmark creates explicitly synthetic data and sends real HTTP
submissions to the real Celery worker. It exercises validation and locked final
testing, progress, persistence, charts' APIs, calibration records, streaming
exports, and output uniqueness:

```sh
docker compose exec api python -m src.tests.gold_consensus_benchmark --seconds 14400 --symbols 35
```

It generates 2,016,000 events over four sessions. To repeat against the same
immutable synthetic dataset, supply `--dataset-id UUID`. The report is written
to `src/tests/artifacts/gold_consensus_performance.json`. A separate real-data
audit reads existing gold level-1 rows without modifying or inventing market
metadata. Synthetic throughput and correctness do not establish profitable
trading, a Gaussian false-alert probability, or latency-realistic performance.

Live operation, historical price-limit annotations, and external NAV anchoring
require their respective verified inputs. Statistical sensitivity/regime studies
require multiple development runs and enough real sessions; a single session
  does not establish uncertainty across regimes.

## September 2026 audit changes

Results and draft settings are separate. Saved headers and exports retain the
run's dataset, policy, source clock, method and evaluation identity. Real data
is the default draft source; synthetic datasets require an explicit demo choice.
The readiness report lists the missing historical inputs and current database
symbols without claiming that current ETF flags establish past membership.

Previous/next decisions, bounded 2,000-second windows, session selection and
Tehran jump-to-time controls read saved outputs. Deep links retain `run_id`,
`method` and an offset-aware `time`. Time axes break missing-score gaps; factor
and ETF charts share a selected-time cursor and window.

Preflight rejects impossible authorized lookback, no session overlap,
unattainable warm-up/outcome bounds and insufficient observation upper bounds.
Passing upper bounds does not guarantee actual grid-change counts, fresh-peer
overlap, nonzero calibration scale, initialization or statistical reliability.
Final-test promotion requires usable scores and outcomes for all three methods
and matching engine and manifest identities. Reusing final data is not fresh
unseen evidence. No alert direction or numerical policy semantics changed.

New imports use version-2 fingerprints binding the canonical full manifest,
frozen database display mapping and observations. New runs snapshot metadata
and record a SHA-256 content identity of the model implementation. Old datasets
and results are not rewritten; legacy display metadata is explicitly unfrozen.
Ordinary exports use symbols; string instrument codes remain internal keys.

The on-demand `/explain` endpoint uses the same filter and saved calibration,
replaying only the selected session prefix without writing outputs. It shows
pre-update exclusion, raw source event, freshness and stored-value agreement.
Full traces are refused for unmatched/unrecorded engine identities, including
legacy runs. Legacy stored outputs remain readable alongside clearly labeled
current-engine source diagnostics. Restart the Celery worker after deployment
so API and worker execute the same implementation.

### Verification on 4 September 2026

No database migration or new dependency was required. The existing menu,
tracked `gold_kalman.replay` task, PostgreSQL lifecycle/calibrations, ClickHouse
outputs, progress units and retry keys are retained. API and idle worker were
restarted; the shared template environment caches templates until restart.

Docker checks: **75 passed**, with one existing TestClient deprecation warning:

```sh
docker compose exec -T -e CACHE_ENABLED=false api python -m pytest \
  src/tests/test_gold_consensus.py src/tests/test_gold_consensus_api.py \
  src/tests/test_gold_consensus_audit.py src/tests/test_admin_chart_templates.py \
  src/tests/test_operation_runs.py -q
```

`qa/gold_kalman_ui_check.js` provides six read-only browser-console checks of
the shipped Tehran conversion and chart-gap helpers. Browser verification also
covered 13:00 method switching, forward/backward windows, deep-link reload,
35-result/3-draft separation, short-default preflight failure, source symbols,
warm-up explanations, matched Kalman/peer-median traces, locked final policy,
cross-session decisions and delayed-response cancellation. Temporary network
and viewport overrides were restored.

Three small replays reused the existing explicitly synthetic 360-event snapshot:
validation `787f6819-0b93-46db-8a3d-c74b5edc2c52`, locked test
`3e001041-bd69-4ae2-a69e-5bb65acbc68a` (576 committed rows each), and two-session
validation `b515a3c0-af58-40d9-ab84-f917a590655a` (1,152 rows).
These use deliberately small verification settings and are not trading defaults
or real-market validation. Existing datasets and previously saved runs were not
rewritten or deleted. Real-history integration remains blocked by the missing
historical input contract described above.
