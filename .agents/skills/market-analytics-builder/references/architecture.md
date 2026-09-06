# Current analytics architecture

## The `options-iv-surface` reference slice

Follow this map when learning the existing design:

| Concern | Current file and symbol |
|---|---|
| Validated request | `src/analytics/iv_config.py` — `IVSurfaceRunConfig` |
| Admin task submission and read APIs | `src/routes/iv_surface.py` — `create_iv_surface_run`, `_checked_run`, run/snapshot/history/export routes |
| Task registration and failure wrapper | `src/tasks.py` — `run_iv_surface` |
| Shared lifecycle/progress | `src/services/operation_runs.py` — `TASK_SPECS`, `enqueue_task`, `RunProgressReporter`, `finish_run`, `fail_run`, `run_to_dict` |
| Celery-wide lifecycle signals | `src/celery_app.py` — `create_scheduled_operation_run`, `start_operation_run`, `complete_operation_run`, `fail_operation_run` |
| Worker computation | `src/analytics/iv_engine.py` — `_load_inputs`, `process_run`, `fail_run` |
| ClickHouse writes and queries | `src/db/clickhouse/iv_surface.py` — `insert_points`, `insert_fits`, timeline/snapshot/history/pagination/stream functions |
| PostgreSQL lifecycle model | `src/db/models/operations.py` — `OperationRun` |
| Main admin page | `src/admin/option/iv_views.py` — `IVSurfaceView` |
| Diagnostic list pages | `src/admin/option/iv_clickhouse_views.py` — `OptionIVPointsView`, `ORCWingFitsView` |
| Shared run history | `src/admin/run_views.py` — `OperationRunsView`, `IVORCRunsView` |
| Main visualization | `src/admin/templates/option/iv_surface.html` |
| Shared run list/progress bar | `src/admin/templates/operations/run_list.html` |
| FastAPI router registration | `src/main.py` |
| SQLAdmin navigation order | `src/admin/__init__.py` — `create_admin` |
| ClickHouse schema | `src/db/clickhouse/migrations/versions/013_option_market_potential_iv_surface.py` |
| PostgreSQL lifecycle migration | `alembic/versions/h8c9d0e1f2g3_standardize_operation_runs.py` |
| Unit/contract tests | `src/tests/test_iv_admin.py`, `src/tests/test_operation_runs.py`, `src/tests/test_admin_chart_templates.py` |
| Browser coverage | `qa/test_options_readonly.py`, `qa/test_options_stateful.py` |

The active flow is:

```text
admin form
  -> POST /admin/tasks/run-iv-surface
  -> validate stock + approved/effective pricing convention
  -> enqueue_task creates PostgreSQL OperationRun(status=queued)
  -> Celery publish carries operation_run_id header
  -> task_prerun marks running
  -> run_iv_surface(run_id)
  -> iv_engine reads immutable config + PostgreSQL metadata + ClickHouse market data
  -> batched option_iv_points/orc_wing_fits writes
  -> RunProgressReporter checkpoints PostgreSQL operation_runs
  -> terminal result/error stored in operation_runs
  -> UI polls task status, links to IV/ORC Runs, then loads compact result APIs
```

`OperationRun.config` and `OperationRun.result` are JSON. `run_to_dict` merges their fields into a convenient response while also returning the nested `config` and `result`. New features should validate `operation.config` directly in the worker when possible. IV's `config_json` and flat duplicated lifecycle fields remain for legacy compatibility and are not a template for a new ClickHouse run table.

## Exact IV menu position

In `create_admin`, IV is in the `# Option Analytics` registration block:

```text
OptionsAnalyticsView
BoxCalculatorView
BoxSpreadView
OptionsMarketPotentialView
IVSurfaceView                 <- main page: after Market Potential, before Mispricing
OptionMispricingView
OptionIVPointsView            <- IV diagnostic table
ORCWingFitsView               <- IV diagnostic table
OptionPricingConventionAdmin
OptionFeeScheduleAdmin
ParityAnalysisSnapshotsView
BoxSpreadSnapshotsView
BoxSpreadPricingsView
```

`IVORCRunsView` is registered later in the source under `# Operations`, after `BoxSpreadRunsView` and before `OptionMispricingRunsView`, although its declared category is still `Options Analytics`. Its details link returns to `/admin/options-iv-surface?run_id=<uuid>`.

For a new feature, agree on both the category and sibling position. Add an order assertion when position matters; an inclusion-only test will not detect accidental movement.

## Lifecycle behavior

`enqueue_task`:

1. resolves the task's `TaskSpec` unless explicit family/type are supplied;
2. creates the queued PostgreSQL row;
3. calls `task.apply_async` with `operation_run_id` and trigger headers;
4. stores the Celery task ID;
5. marks the run failed if publishing raises.

Celery signals make direct/Beat publication observable too. `before_task_publish` creates a scheduled run only when the publisher did not already attach a run ID. `task_prerun` marks running, `task_postrun` calls `finish_run` on success, and `task_failure` records the error. This is why tasks must be in `TASK_SPECS`.

The worker should still load the run and reject an unknown family/model version. A task-specific wrapper may add logging or final-retry handling, but it must re-raise failures so Celery and the lifecycle record agree.

Terminal statuses are `completed`, `failed`, or `skipped`. `finish_run` moves progress to the known total, derives a useful output count from common result keys, and preserves warning counts. Results are converted to JSON-safe values; non-finite floats become null.

## Progress as currently shown

There are two related UI paths:

- The IV form polls `/admin/tasks/status/{task_id}` every two seconds. Today it shows the textual status and a link to `/admin/iv-orc-runs?run_id=...`; it does not render a live numeric percentage.
- `operations/run_list.html` renders the durable numeric bar from `progress_current / progress_total`, plus output count, warning count, duration, expandable config/result/error, and a feature details link.

Checkpoint `result` can contain feature-specific live counts. If a new page needs an in-place numeric bar, use the feature run-detail API, or make a deliberate shared API change so both current and total are returned. Do not claim the generic status endpoint already returns those fields.

## Output and interaction design

IV writes large, run-scoped analytical records to ClickHouse in batches. It preserves both accepted and rejected point observations, then writes fitted rows with convergence and quality flags. Its completion result contains snapshot, point, fit, warning, and timing counts.

The UI intentionally avoids the bulk `/points`, `/fits`, and `/grid` routes during interaction:

- `/timeline` returns only distinct snapshot times and expiries;
- `/snapshot` returns chart-ready accepted points, fits, generated grid, and rejection counts for one time;
- `/history` returns one expiry/side's intraday fit and forward series;
- the browser aborts stale snapshot requests and keeps a small cache with bounded prefetch;
- `/export.csv` streams all raw points by ClickHouse row blocks and appends run provenance.

Use this access-pattern-first design for new analytics. A heatmap, ranking, replay slider, and raw audit table usually need different endpoints.

## Nearby patterns to compare

- `src/admin/gold/analytics_views.py` + `GoldBestQuotesChartView`: direct read-only analytics with no materialized run.
- `src/analytics/market_potential.py` + `compute_option_market_potential_daily`: scheduled daily materialization.
- `src/analytics/parity_engine.py`: focused immutable replay.
- `src/analytics/box_spread_engine.py`: focused pair analysis with visualization details.
- `src/analytics/mispricing_engine.py`: market-wide scan, frozen universe, retry-aware wrapper, rankings and drill-down.
- `src/tasks.py` yield-curve backfill: simple per-date use of `RunProgressReporter.advance`.

