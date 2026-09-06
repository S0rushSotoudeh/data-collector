# Market analytics implementation checklist

Use only the sections required by the chosen execution shape. A direct read-only chart does not need run tracking, a task, or output migrations.

## 1. Product and quantitative contract

- [ ] Name the market, analytic, user decision it supports, and expected page/menu location.
- [ ] Define input sources and confirm their date/time coverage and granularity.
- [ ] Specify price/currency/quantity/rate units, market timezone, calendar/session rules, and any corporate-action or contract multiplier handling.
- [ ] Define equations/model assumptions and a version identifier when results can change as code evolves.
- [ ] Define valid, rejected/flagged, empty, skipped, and failed outcomes.
- [ ] Decide whether the computation is direct, scheduled materialization, or a tracked background run.
- [ ] For reproducibility, decide whether metadata/universe is frozen at submission, rediscovered at worker start, or versioned by effective date. Record the choice.

## 2. Data model and migrations

- [ ] Reuse PostgreSQL `OperationRun`; do not add another lifecycle table.
- [ ] Add PostgreSQL models/Alembic only for durable relational metadata, approvals, or conventions the analytic actually needs.
- [ ] Add a numbered ClickHouse migration for new analytical outputs, with reversible `upgrade(client)` and `downgrade(client)`.
- [ ] Include `run_id` in every tracked-run output and lead the ordering key with fields used to isolate/drill into a run.
- [ ] Choose partitioning for retention and pruning, commonly a market/trade month rather than run creation time.
- [ ] Choose `MergeTree`/`ReplacingMergeTree`, version column, and `FINAL` policy based on whether writes can repeat.
- [ ] Add provenance and quality columns; avoid storing only a final score that cannot be explained.
- [ ] Add typed insert helpers and parameterized, filtered query helpers. Keep async reads separate from synchronous worker writes as current modules do.
- [ ] Add count + pagination for operator tables and block streaming for large exports.

## 3. Run configuration and lifecycle

- [ ] Create a Pydantic config near the analytic with range and cross-field validation.
- [ ] Use stable identifiers: `family`, dotted `run_type`, and `target`.
- [ ] Calculate the progress denominator before enqueue when practical.
- [ ] Submission route authenticates, validates live metadata/effective dates, and calls `enqueue_task` before returning.
- [ ] Return `run_id`, `task_id`, and queued status; include only small useful submission metadata.
- [ ] Add the task to `TASK_SPECS`, including tasks intended only for manual use.
- [ ] If scheduled, add the Beat entry and environment-backed schedule setting; rely on the publish signal to create the scheduled lifecycle row.
- [ ] Add a family-checked run-detail endpoint and a paginated run-list endpoint.
- [ ] Keep secrets and large discovered inputs out of `OperationRun.config` and Celery messages.

## 4. Worker and progress

- [ ] Worker loads the run, checks family/model version, parses immutable config, and revalidates mutable prerequisites.
- [ ] Read relational reference data from PostgreSQL and time-series inputs from ClickHouse.
- [ ] Make batch size explicit and bounded; flush at deterministic boundaries.
- [ ] Call `RunProgressReporter.set_total` and use either delta `advance` or absolute `checkpoint` correctly.
- [ ] Report only monotonic progress. Include live result counts when useful.
- [ ] Separate row-level exclusions/quality warnings from run-level exceptions.
- [ ] Store terminal processed/output/warning counts and coarse phase timings.
- [ ] Log run ID and meaningful phase/result context. Never log credentials or huge payloads.
- [ ] Re-raise infrastructure or invariant failures.
- [ ] If retries are enabled, prove idempotent writes or perform scoped cleanup before a retry. Do not mark a retrying attempt terminally failed.

## 5. Authenticated API

- [ ] Import and include the router in `src/main.py`.
- [ ] Protect submit, status/detail, data, and export endpoints with `_require_admin`.
- [ ] Scope every tracked result query by validated run ID and verify the run belongs to the expected family.
- [ ] Use constrained query parameters and parameterized SQL.
- [ ] Return compact endpoints matching UI interactions rather than one unbounded payload.
- [ ] Handle empty results consistently; return 404 only when the run or explicitly requested entity/snapshot truly does not exist.
- [ ] Stream large exports and embed config/model/source provenance in the export.

## 6. Admin page and navigation

- [ ] Use `BaseView` + shared `_render()` + `self._admin_ref` and all mandatory template context keys.
- [ ] Use a unique identity and stable path.
- [ ] Set the market analytics category and icon.
- [ ] Register the main page at the exact intended sibling position in `create_admin`.
- [ ] Add diagnostic `ClickHouseListView` pages only when operators need raw records.
- [ ] Add an `OperationRunsView` subclass for a new tracked family and a family-specific details link back to the analytic.
- [ ] Register run/detail/list pages deliberately and test their relative order when the user specifies position.
- [ ] Extend `shared/admin_base.html`; include shared ECharts support for charts.
- [ ] Show ready, queued, running, completed, skipped, failed, empty, and load-error states.
- [ ] Poll at a bounded interval, stop at terminal state, and link to the run record on failure.
- [ ] If showing numeric live progress, fetch both current and total from a contract that actually exposes them.
- [ ] Deep-link saved runs with `?run_id=...` and make run-history details return to that URL.
- [ ] Cancel stale browser requests and bound caches/prefetch for slider or drill-down interactions.
- [ ] Verify labels, numbers, currencies, rates, axes, tooltips, empty charts, and mobile overflow.

## 7. Tests

- [ ] Pure analytic unit tests cover known examples, bounds, invalid inputs, units, and numerical edge cases.
- [ ] Engine tests cover no data, partial data, rejected observations, successful batches, quality warnings, and failure propagation.
- [ ] Operation tests cover task/spec registration, queued-to-terminal transitions, scheduled header propagation, progress checkpoints, and retry behavior.
- [ ] ClickHouse query tests assert run/time scoping, parameter types, deterministic ordering, pagination, zero/empty filters, and absence/presence of `FINAL` as designed.
- [ ] Migration tests cover upgrade, downgrade, history/pending/check, and expected table definitions.
- [ ] Route tests cover authentication, 422 validation, missing/wrong-family runs, empty output, successful output, and streamed export headers/content.
- [ ] Template tests compile the page and enforce shared chart utilities and compact endpoint usage.
- [ ] Admin tests assert category, unique identity, registration, intended order, and details links.
- [ ] Read-only browser tests open every new route, use a known saved run, exercise filters/drill-down/export, and assert a clean console/page.
- [ ] Stateful browser tests are narrowly gated (the current suite requires `E2E_ENABLE_STATEFUL=1`) and submit a minimal bounded run.

## 8. Verification sequence

- [ ] Run targeted tests inside the `api` Docker Compose service.
- [ ] Run affected shared operation, migration, route, and template suites.
- [ ] Apply/check migrations inside Docker against a disposable or approved environment.
- [ ] With services running, verify API auth, enqueue response, worker logs, progress movement, terminal state, result queries, run details link, export, and narrow viewport.
- [ ] Run Graphify update after each code change and query changed symbols plus callers/callees.
- [ ] Review `git diff` and preserve unrelated user changes.
- [ ] Handoff includes exact commands/results and any deployment or operator steps still required.

