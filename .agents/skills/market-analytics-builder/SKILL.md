---
name: market-analytics-builder
description: Add or extend a first-class market analytics feature in data_collector, including computation, tracked Celery runs, progress, ClickHouse outputs, authenticated APIs, SQLAdmin pages, menu placement, exports, migrations, and tests. Use for analytics over gold, options, bonds, stocks, crypto, or IME; do not use for raw-data collection alone.
---

# Market Analytics Builder

Build analytics as an intentional vertical slice. Use `options-iv-surface` as the main reference, but preserve the new analytic's own domain, data grain, latency, and reproducibility requirements instead of cloning every IV-specific detail.

## Start with repository discovery

1. Read and follow `../graphify/SKILL.md` before opening implementation files. Graphify is mandatory in this repository.
2. Query the proposed analytic, its source tables, the nearest existing market page, `OperationRun`, `RunProgressReporter`, `enqueue_task`, `TASK_SPECS`, and `create_admin`.
3. Read [references/architecture.md](references/architecture.md) for the current IV-surface flow, shared infrastructure, progress contract, and menu rules.
4. Read [references/implementation-checklist.md](references/implementation-checklist.md) before editing and again before handoff.
5. Inspect the closest sibling analytic as well as IV surface. Prefer the sibling whose execution shape matches the request: live read-only chart, scheduled materialization, focused replay, or market-wide scan.

## Choose the smallest correct execution shape

- Use a direct authenticated read API and admin page when the query is bounded, fast, and does not materialize a new result set. `GoldBestQuotesChartView` is the local example.
- Use a scheduled Celery materialization when the same daily aggregate should be computed once and reused. Option market potential is the local example.
- Use a tracked background run when an admin selects inputs, the work can outlive an HTTP request, progress matters, results must be replayable, or partial/failed work needs diagnosis. IV surface, parity, box spread, and option mispricing are local examples.
- Do not add a background task merely to wrap a cheap query. Do not perform a long replay in a FastAPI request.
- Keep collection and analytics separate. Reuse collected raw data; expand collection only when the requested analytic genuinely lacks required inputs.

State the chosen shape and why before implementation. If it is a tracked run, define these contracts first:

- stable `family`, dotted `run_type`, and human-readable `target`;
- immutable validated run config and input/provenance fields;
- exact unit of progress and how `progress_total` is known;
- output grain, primary ordering key, partitioning, and retry/idempotency behavior;
- row-level quality/rejection outcomes versus run-level failure;
- chart/list/export access patterns and expected maximum result size;
- manual, scheduled, or both trigger modes.

## Canonical tracked-run rules

- PostgreSQL `operation_runs` is the only canonical lifecycle store for new work. Do not create a feature-specific ClickHouse run table. The existing `iv_surface_runs` table is legacy and current IV code no longer writes it.
- Put analytical time-series and large outputs in ClickHouse. Put relational metadata, approvals, conventions, and the lifecycle row in PostgreSQL.
- Validate twice where correctness depends on mutable metadata: reject bad submissions in the route for fast feedback, then revalidate in the worker before computation.
- Create the lifecycle row before publishing the task by calling `enqueue_task`. Return both `run_id` and `task_id`.
- Pass the `run_id` into the worker and propagate it to every output row. Keep the task message small; do not send a discovered universe or large dataset through Redis.
- Add every `@shared_task` in `src/tasks.py` to `TASK_SPECS`. A repository test intentionally requires exact equality between registered application tasks and specs.
- Let exceptions escape the task after logging. Celery signals finalize tracked runs. If the task retries, mark it failed only after the final attempt, and make output writes safe to repeat.
- Store a useful terminal result: processed work units, output rows, warnings/rejections, and coarse phase timings. Keep operational errors in `OperationRun.error`; do not disguise them as quality warnings.

## Progress contract

Use `RunProgressReporter` from `src/services/operation_runs.py`.

- Call `set_total(total)` once the real total is known. Prefer determining it before enqueue so queued pages already have a denominator.
- Use `advance(output_count=delta, warning_count=delta)` when each loop iteration is one work unit. These counts are deltas.
- Use `checkpoint(current, output_count=absolute, warning_count=absolute, result=...)` for nested loops or externally known absolute positions. These counts are absolute.
- The reporter persists at 5-percent boundaries by default and at completion, limiting PostgreSQL write load.
- Count durable, understandable work units such as dates, snapshots, instruments, partitions, or frozen universe members. Never use an arbitrary loop count that can regress or change mid-run.
- Flush result batches before reporting them as durable when users may interpret output counts as committed rows. If in-memory rows are shown, label that meaning explicitly.
- The generic `/admin/tasks/status/{task_id}` response exposes `status`, checkpoint `result`, and `error`; it does not expose `progress_current` or `progress_total` as top-level fields. For a numeric progress bar, fetch the feature's run-detail endpoint or deliberately extend the shared response and its tests.
- Stop polling on lowercase application terminal states (`completed`, `failed`, `skipped`) and tolerate uppercase Celery fallback states (`SUCCESS`, `FAILURE`). Surface a link to the family run page on failure.

## Admin and menu contract

- Custom pages must use `BaseView`, the shared manual `_render()` helper, and `self._admin_ref`. Supply `request`, `admin`, `url_for`, `title`, and `subtitle`.
- Give every view a unique `identity`, stable exposed path, suitable icon, and a market-specific category such as `Gold Analytics`, `Bond Analytics`, or `Options Analytics`.
- Menu position is controlled in `src/admin/__init__.py` by `admin.add_view(...)` registration order. Put the main analytic page in the relevant `# <Market> Analytics` block at the requested sibling position. Register raw/detail tables immediately after related user-facing pages unless the product design calls for another location.
- A run-history view may reuse `OperationRunsView`, but add its family-specific details link in `OperationRunsView._runs` and register the view intentionally. Do not assume adding a Celery task creates navigation.
- Import and include the feature router in `src/main.py`. Protect all task and data APIs with `_require_admin`; SQLAdmin page authentication does not protect standalone FastAPI routes automatically.
- For charts, extend `shared/admin_base.html`, include `shared/echarts_support.html`, initialize charts through `AdminCharts`, handle empty/loading/error states, and verify narrow-screen overflow.
- Drive large visualizations with compact endpoints tailored to interaction. IV surface loads a timeline, one snapshot, and one expiry/side history instead of downloading all points and fits. Cancel stale fetches and cache/prefetch only bounded nearby data when interaction benefits.
- Provide filtered, paginated browse pages through `ClickHouseListView` when operators need raw diagnostics. Stream large CSV exports in ClickHouse blocks rather than materializing the entire export in API memory.

## Data and correctness rules

- Use parameterized ClickHouse queries, explicit result columns for chart endpoints, deterministic ordering, and `run_id` scoping on every run-specific query.
- Preserve provenance needed to explain a value later: source timestamps, quote age, rate/source, convention or model version, market timezone, input range, and rejection/quality reason as applicable.
- Treat units and conversions as part of the validated contract. Never silently substitute zero or a different market convention for missing reference data.
- Choose ClickHouse engine, version column, `FINAL` usage, partition key, and ordering key together with the retry strategy. A retryable task must not create duplicate visible rows.
- Use Tehran-aware datetimes for Iranian-market event time where the surrounding tables do. Keep lifecycle timestamps compatible with PostgreSQL's timezone-aware columns.
- Return valid empty responses for no-data ranges. Reserve run failure for broken invariants or infrastructure errors; record expected bad observations as rejected/flagged output when that helps diagnosis.
- Avoid unbounded `SELECT *` and arbitrary hard limits in interactive pages. Add pagination, drill-down endpoints, or streaming based on the actual access pattern.

## Verification and handoff

All application commands run through Docker Compose. Use targeted tests first, then the broader affected suite. Typical commands are:

```text
docker compose exec api python -m pytest src/tests/test_<feature>.py
docker compose exec api python -m pytest src/tests/test_operation_runs.py src/tests/test_admin_chart_templates.py
docker compose exec api python manage.py clickhouse check
docker compose exec api alembic upgrade head
```

After every code change, run the mandatory repository Graphify update and query the changed symbols and callers/callees again. At handoff, report:

- chosen execution shape and menu position;
- run family/type/target and progress unit;
- lifecycle store and each output table;
- routes, page paths, history/detail links, and export behavior;
- retry/idempotency decision and quality/failure semantics;
- migrations and exact tests run;
- any required deployment config, Beat schedule, backfill, or operator action.

