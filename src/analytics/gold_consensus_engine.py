from __future__ import annotations

import math
import resource
import time
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache

import numpy as np
from sqlalchemy import text

from src.analytics.gold_consensus import calibrate, filter_grid, outcome_arrays, reconstruct
from src.analytics.gold_consensus_config import DatasetManifest, GoldKalmanRunConfig
from src.db.clickhouse.gold_consensus import get_client, dataset_row, insert_rows, load_events
from src.db.models.gold_consensus import GoldKalmanCalibration
from src.db.session import SessionLocal, engine
from src.services.operation_runs import RunProgressReporter, get_run


def validate_inputs(config: GoldKalmanRunConfig):
    dataset = dataset_row(config.dataset_id)
    if dataset is None or dataset.status != "ready":
        raise ValueError("dataset is missing or has not passed import validation")
    manifest = DatasetManifest.model_validate(dataset.manifest)
    universe = {s for item in manifest.sessions for s in item.eligible_symbols}
    if not set(config.symbols) <= universe:
        raise ValueError("selected symbols are absent from dataset eligibility")
    if manifest.sessions[0].open > config.history_from or manifest.sessions[-1].close < config.test_to:
        raise ValueError("dataset calendar must cover the complete authorized history and evaluation ranges")
    if config.mode == "test":
        reference = get_run(config.validation_run_id)
        if (reference is None or reference.family != "gold_kalman" or reference.status != "completed"
                or reference.config.get("policy_hash") != config.policy_hash()
                or reference.config.get("policy", {}).get("mode") != "validation"
                or reference.config.get("dataset_sha256") != dataset.sha256):
            raise ValueError("test policy/dataset must match a completed validation run")
    return dataset, manifest


def jobs(config, manifest):
    start, end = config.evaluation_bounds()
    return [(i, max(s.open, start).timestamp(), min(s.close, end).timestamp())
            for i, s in enumerate(manifest.sessions) if s.open < end and s.close > start]


def progress_total(config, manifest):
    return 1 + sum(1 + 3 * max(0, math.ceil(end) - math.ceil(start)) for _, start, end in jobs(config, manifest))


def save_fit(run_id, session, method, fit):
    fit_id = uuid.uuid5(uuid.UUID(str(run_id)), session.open.isoformat() + method)
    with SessionLocal() as db:
        previous = db.get(GoldKalmanCalibration, fit_id)
        if previous:
            if previous.payload != fit:
                raise ValueError("immutable calibration changed on replay")
        else:
            db.add(GoldKalmanCalibration(calibration_id=fit_id, run_id=uuid.UUID(str(run_id)),
                   session_open=session.open, method=method, payload=fit))
            db.commit()
    return fit_id


def number(value):
    return float(value) if np.isfinite(value) else None


def persist_session(client, run_id, method, range_name, fit_id, grid, fit, scores, outcomes, config):
    buffers = {kind: [] for kind in ("scores", "market", "outcomes")}
    rows_written = 0
    micro, mids = grid.micro, grid.mid
    calibrated = set(fit.get("symbols", []))
    for t, stamp in enumerate(grid.times):
        when = datetime.fromtimestamp(float(stamp), timezone.utc)
        common = [uuid.UUID(str(run_id)), method, range_name, when, fit_id]
        market = scores["market"][t]
        peers = [j for j, s in enumerate(config.symbols) if s in calibrated and grid.valid[t, j]]
        reason = "" if market[5] else (fit.get("reason", "") if not fit.get("available") else
                    "insufficient_coverage" if market[2] < 3 else "initialization_or_warmup")
        buffers["market"].append(common + [number(market[0]), number(market[1]), int(market[2]),
            number(market[3]), number(market[4]), int(market[5]), reason,
            [config.symbols[j] for j in peers], [float(mids[t, j]) for j in peers]])
        for j in np.flatnonzero(np.isfinite(scores["z"][t])):
            bid, ask, qb, qa = grid.books[t, j]
            fair = scores["fair"][t, j]
            persistent = int(scores["persistence"][t, j])
            buffers["scores"].append(common + [config.symbols[j], float(micro[t, j]), float(mids[t, j]),
                float(bid), float(ask), float(fair), float(scores["z"][t, j]), float(scores["delta"][t, j]),
                float(scores["benchmark_variance"][t, j]), float(10000 * (micro[t, j] / fair - 1)),
                float(10000 * (fair / ask - 1)), float(10000 * (bid / fair - 1)),
                float(10000 * (ask - bid) / mids[t, j]), float((qb - qa) / (qb + qa)),
                float(stamp - grid.quote_times[t, j]), int(market[2]), persistent, int(persistent >= config.k)])
            available = bool(outcomes["available"][t, j])
            reason = "" if available else "range_or_session_boundary" if stamp + config.analysis_horizon_seconds >= outcomes["end"] else "missing_or_invalid_original_peer"
            buffers["outcomes"].append(common + [config.symbols[j], config.analysis_horizon_seconds,
                int(available), reason, *[number(outcomes[key][t, j]) for key in
                    ("relative", "recovery", "reduction", "micro_error", "mid_error")]])
        if sum(map(len, buffers.values())) >= 25000:
            for kind, rows in buffers.items():
                insert_rows(client, kind, rows)
                rows_written += len(rows)
                rows.clear()
    for kind, rows in buffers.items():
        insert_rows(client, kind, rows)
        rows_written += len(rows)
    return rows_written


def summary(scores, outcomes, grid, config):
    published = np.isfinite(scores["z"])
    count = int(published.sum())
    valid = outcomes["available"]
    def mean(key):
        values = outcomes[key][valid]
        return float(np.mean(values)) if values.size else None
    ages = grid.times[:, None] - grid.quote_times
    observed = np.isfinite(grid.quote_times)
    return {"score_count": count, "outcome_count": int(valid.sum()),
            "missing_outcome_rate": 1 - float(valid.sum()) / count if count else None,
            "mean_recovery_log_bps": mean("recovery"), "mean_gap_reduction_log_bps": mean("reduction"),
            "overshoot_count": int(((outcomes["recovery"] > 0) & (outcomes["reduction"] < 0)).sum()),
            "mean_micro_error_log_bps": mean("micro_error"), "mean_mid_error_log_bps": mean("mid_error"),
            "exceedance_count": int((np.abs(scores["z"]) >= config.z_alert).sum()),
            "persistent_count": int((scores["persistence"] >= config.k).sum()),
            "suppressed_timestamps": int((scores["market"][:, 5] == 0).sum()),
            "mean_coverage": float(np.mean(scores["market"][:, 2])) if len(grid.times) else 0,
            "new_measurements": int((grid.valid & grid.new).sum()),
            "stale_observations": int((observed & (ages > config.max_quote_age)).sum()),
            "phase_observations": {name: int((observed & (grid.phases == code)).sum())
                                   for code, name in enumerate(("unknown", "continuous", "auction", "halted"))},
            "mean_scored_quote_age": float(np.mean(ages[published])) if count else None,
            "max_scored_quote_age": float(np.max(ages[published])) if count else None,
            "residual_std_by_symbol": {symbol: float(np.std(scores["delta"][:, j][published[:, j]]))
                 for j, symbol in enumerate(config.symbols) if published[:, j].any()}}


def process_run(run_id):
    # A session-scoped PG advisory lock serializes duplicate deliveries; deterministic
    # ClickHouse replacement keys make partially written runs safe to replay.
    lock_key = uuid.UUID(str(run_id)).int % (2**63 - 1)
    with engine.connect() as lock:
        lock.execute(text("SELECT pg_advisory_lock(:key)"), {"key": lock_key})
        try:
            return _process_run(run_id)
        finally:
            lock.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": lock_key})


def _process_run(run_id):
    operation = get_run(run_id)
    if operation is None or operation.family != "gold_kalman":
        raise ValueError("unknown gold Kalman run")
    if operation.status == "completed":
        return operation.result
    config = GoldKalmanRunConfig.model_validate(operation.config["policy"])
    dataset, manifest = validate_inputs(config)
    if dataset.sha256 != operation.config["dataset_sha256"] or config.policy_hash() != operation.config["policy_hash"]:
        raise ValueError("immutable input identity changed")
    client = get_client()
    reporter = RunProgressReporter(run_id)
    reporter.set_total(progress_total(config, manifest))
    timings = defaultdict(float)
    run_started = time.perf_counter()

    @lru_cache(maxsize=config.calibration_lookback_sessions + 1)
    def history_grid(index):
        start = time.perf_counter()
        session = manifest.sessions[index]
        events = load_events(config.dataset_id, index, client)
        times = np.arange(math.ceil(session.open.timestamp()), session.close.timestamp())
        grid = reconstruct(events, config.symbols, times, session.open.timestamp(), session.close.timestamp(),
                           config.max_quote_age, set(session.eligible_symbols))
        timings["history_read_reconstruction_seconds"] += time.perf_counter() - start
        return grid

    def session_fit(index):
        start = time.perf_counter()
        session = manifest.sessions[index]
        selected = list(range(index - config.calibration_lookback_sessions, index))
        base = {"cutoff": session.open.isoformat(), "effective_time": session.open.isoformat(),
                "selected_sessions": [manifest.sessions[i].open.isoformat() for i in selected if i >= 0],
                "model_version": config.model_version, "policy_hash": config.policy_hash()}
        if min(selected) < 0 or manifest.sessions[min(selected)].open < config.history_from:
            return base | {"available": False, "reason": "insufficient_authorized_history"}
        grids = [history_grid(i) for i in selected]
        fit = calibrate(grids, config.symbols, config)
        base["missing_sessions"] = [manifest.sessions[i].open.isoformat() for i, g in zip(selected, grids) if not g.valid.any()]
        timings["calibration_including_history_seconds"] += time.perf_counter() - start
        return base | fit

    first_validation = next((i for i, s in enumerate(manifest.sessions) if s.close > config.validation_from and s.open < config.validation_to), None)
    frozen = session_fit(first_validation) if first_validation is not None else {"available": False, "reason": "no_validation_session"}
    reporter.advance()
    reports, output_count, warning_count = [], 0, 0
    for index, start, end in jobs(config, manifest):
        session = manifest.sessions[index]
        scheduled = session_fit(index)
        reporter.advance()
        began = time.perf_counter()
        events = load_events(config.dataset_id, index, client)
        times = np.arange(math.ceil(start), end)
        grid = reconstruct(events, config.symbols, times, start, end, config.max_quote_age, set(session.eligible_symbols))
        endpoint = reconstruct(events, config.symbols, times + config.analysis_horizon_seconds, start, end,
                               config.max_quote_age, set(session.eligible_symbols))
        timings["evaluation_read_reconstruction_seconds"] += time.perf_counter() - began
        method_outputs = {}
        for method, fit in (("scheduled", scheduled), ("frozen", frozen), ("peer_median", scheduled)):
            fit_id = save_fit(run_id, session, method, fit)
            began = time.perf_counter()
            scores = filter_grid(grid, config.symbols, fit, config, method)
            timings["filter_seconds"] += time.perf_counter() - began
            began = time.perf_counter()
            outcomes = outcome_arrays(grid, endpoint, scores, config.analysis_horizon_seconds, end,
                                       set(fit.get("symbols", [])), config.symbols)
            outcomes["end"] = end
            timings["outcome_seconds"] += time.perf_counter() - began
            began = time.perf_counter()
            output_count += persist_session(client, run_id, method, config.mode, fit_id, grid, fit, scores, outcomes, config)
            timings["persistence_seconds"] += time.perf_counter() - began
            warning_count += len(fit.get("exclusions", {})) + int(not fit.get("available"))
            report = {"session_open": session.open.isoformat(), "method": method, "calibration_id": str(fit_id),
                      **summary(scores, outcomes, grid, config)}
            reports.append(report)
            method_outputs[method] = (scores, outcomes, report)
            reporter.checkpoint(reporter.current + len(times), output_count=output_count, warning_count=warning_count,
                result={"phase": "replay", "session": session.open.isoformat(), "method": method,
                        "total_rows": output_count, "timings": dict(timings)})
        common = np.logical_and.reduce([np.isfinite(values[0]["z"]) for values in method_outputs.values()])
        common_outcomes = np.logical_and.reduce([values[1]["available"] for values in method_outputs.values()])
        for _, outcomes, report in method_outputs.values():
            report["common_score_count"] = int(common.sum())
            report["common_outcome_count"] = int(common_outcomes.sum())
            report["common_mean_recovery_log_bps"] = float(np.mean(outcomes["recovery"][common_outcomes])) if common_outcomes.any() else None
            report["common_mean_gap_reduction_log_bps"] = float(np.mean(outcomes["reduction"][common_outcomes])) if common_outcomes.any() else None
    timings["wall_seconds"] = time.perf_counter() - run_started
    timings["worker_peak_rss_mb"] = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024
    return {"status": "completed" if reports else "skipped", "total_rows": output_count,
            "warning_count": warning_count, "sessions": reports, "timings": dict(timings),
            "clock": manifest.clock, "dataset_sha256": dataset.sha256, "policy_hash": config.policy_hash(),
            "interpretation": "Relative-price diagnostics; excludes fees and hedge costs; session-level comparisons, not independent tick tests."}
