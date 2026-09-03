"""Causal scalar consensus, deliberately independent of databases and Celery.

Events are (available_at, quote_time, sequence, bid, ask, bid_qty, ask_qty,
continuous_phase). Times are UTC epoch seconds; prices are IRR. The same
as-of reconstruction is used for calibration, replay, and exact-horizon labels.
"""
from __future__ import annotations

import math
import warnings
from dataclasses import dataclass

import numpy as np

from src.analytics.gold_consensus_config import GoldKalmanRunConfig


@dataclass
class Grid:
    times: np.ndarray
    books: np.ndarray
    quote_times: np.ndarray
    valid: np.ndarray
    new: np.ndarray
    phases: np.ndarray

    @property
    def mid(self):
        return (self.books[:, :, 0] + self.books[:, :, 1]) / 2

    @property
    def micro(self):
        b = self.books
        with np.errstate(divide="ignore", invalid="ignore"):
            return (b[:, :, 1] * b[:, :, 2] + b[:, :, 0] * b[:, :, 3]) / (b[:, :, 2] + b[:, :, 3])


def canonical_events(raw: np.ndarray) -> np.ndarray:
    if not len(raw):
        return np.empty((0, 8), dtype=float)
    raw = np.asarray(raw, dtype=float)
    if raw.ndim != 2 or raw.shape[1] != 8 or not np.isfinite(raw).all():
        raise ValueError("events require eight finite numeric fields")
    if np.any(raw[:, 1] > raw[:, 0]) or np.any(raw[:, 2] < 0) or np.any(raw[:, 2] != np.floor(raw[:, 2])):
        raise ValueError("future quote time or invalid source sequence")
    if np.any(raw[:, 2] > 2**53):
        raise ValueError("sequence exceeds exact numeric representation")
    rows = raw[np.lexsort((raw[:, 2], raw[:, 0]))]
    # Identity is quote time + sequence. Retransmission cannot refresh arrival,
    # revive an invalid book, or reduce uncertainty.
    seen = {}
    keep = []
    for row in rows:
        key = (row[1], row[2])
        signature = tuple(row[3:])
        if key in seen:
            if seen[key] != signature:
                raise ValueError("conflicting source event identity")
            continue
        seen[key] = signature
        keep.append(row)
    rows = np.asarray(keep)
    if len(rows) > 1:
        same = (rows[1:, 0] == rows[:-1, 0]) & (rows[1:, 2] == rows[:-1, 2])
        if same.any():
            raise ValueError("ambiguous source order within timestamp")
    # Late delivery of an older source state must not undo a newer book.
    retained = []
    last_source = (-math.inf, -1)
    for row in rows:
        source = (row[1], row[2])
        if source > last_source:
            retained.append(row)
            last_source = source
    rows = np.asarray(retained)
    return rows


def reconstruct(events: dict[str, np.ndarray], symbols: list[str], times: np.ndarray,
                start: float, end: float, max_age: float, eligible: set[str]) -> Grid:
    shape = (len(times), len(symbols))
    books = np.full((*shape, 4), np.nan)
    quote_times = np.full(shape, np.nan)
    valid = np.zeros(shape, dtype=bool)
    new = np.zeros(shape, dtype=bool)
    phases = np.zeros(shape, dtype=np.uint8)
    for j, symbol in enumerate(symbols):
        rows = events.get(symbol, np.empty((0, 8)))
        rows = rows[(rows[:, 0] >= start) & (rows[:, 0] < end)]
        if not len(rows) or symbol not in eligible:
            continue
        indices = np.searchsorted(rows[:, 0], times, side="right") - 1
        present = indices >= 0
        selected = rows[np.maximum(indices, 0)]
        books[present, j] = selected[present, 3:7]
        quote_times[present, j] = selected[present, 1]
        phases[present, j] = selected[present, 7].astype(np.uint8)
        b = books[:, j]
        ages = times - quote_times[:, j]
        valid[:, j] = (present & (b[:, 0] > 0) & (b[:, 1] > b[:, 0]) &
                       (b[:, 2] > 0) & (b[:, 3] > 0) & (ages >= 0) &
                       (ages <= max_age) & (selected[:, 7] == 1))
        signature = selected[:, 3:8]
        changed = np.ones(len(times), dtype=bool)
        if len(times) > 1:
            changed[1:] = np.any(signature[1:] != signature[:-1], axis=1) | ~present[:-1]
        new[:, j] = present & changed
    return Grid(times, books, quote_times, valid, new, phases)


def peer_medians(values: np.ndarray) -> np.ndarray:
    """Exact leave-one-out medians in O(N log N), for finite 1D values."""
    n = len(values)
    if n < 2:
        return np.full(n, np.nan)
    order = np.argsort(values, kind="stable")
    sorted_values = values[order]
    ranks = np.arange(n)
    lo, hi = (n - 2) // 2, (n - 1) // 2
    out = np.empty(n)
    out[order] = (sorted_values[lo + (ranks <= lo)] + sorted_values[hi + (ranks <= hi)]) / 2
    return out


def calibrate(grids: list[Grid], symbols: list[str], config: GoldKalmanRunConfig) -> dict:
    excluded = {}
    if not grids or not any(len(g.times) for g in grids):
        return {"available": False, "reason": "missing_calibration_history", "exclusions": excluded}
    micro = np.concatenate([g.micro for g in grids])
    valid = np.concatenate([g.valid for g in grids])
    fresh = np.concatenate([g.new for g in grids])
    logp = np.log(np.where(valid, micro, 1))
    eligible = np.arange(len(symbols))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        while len(eligible) >= 3:
            mask = valid[:, eligible].copy()
            mask &= (mask.sum(axis=1) >= 3)[:, None]
            counts = (mask & fresh[:, eligible]).sum(axis=0)
            supported = counts >= config.min_calibration_observations
            if not supported.all():
                for j in eligible[~supported]:
                    excluded[symbols[j]] = "insufficient_distinct_observations"
                eligible = eligible[supported]
                continue
            y = np.where(mask, logp[:, eligible], np.nan)
            center = np.nanmedian(y, axis=1)
            alpha = np.nanmedian(y - center[:, None], axis=0)
            normalized = y - alpha
            residual = np.empty_like(normalized)
            for j in range(len(eligible)):
                residual[:, j] = normalized[:, j] - np.nanmedian(np.delete(normalized, j, axis=1), axis=1)
            mad = np.nanmedian(np.abs(residual - np.nanmedian(residual, axis=0)), axis=0)
            supported = np.isfinite(alpha) & np.isfinite(mad) & (mad > 0)
            if not supported.all():
                for j in eligible[~supported]:
                    excluded[symbols[j]] = "zero_or_nonfinite_residual_scale"
                eligible = eligible[supported]
                continue
            r = np.maximum((1.4826 * mad) ** 2, 1e-12)
            references, intervals = [], []
            for g in grids:
                usable = g.valid[:, eligible]
                usable &= (usable.sum(axis=1) >= 3)[:, None]
                weight = ((usable & g.new[:, eligible]) / r).sum(axis=1)
                ix = np.flatnonzero(weight > 0)
                references.extend(1 / weight[ix])
                # A loss of three-book coverage breaks the reference interval.
                good = usable.sum(axis=1) >= 3
                bad_prefix = np.cumsum(~good)
                for left, right in zip(ix[:-1], ix[1:]):
                    if bad_prefix[right] == bad_prefix[left]:
                        intervals.append(g.times[right] - g.times[left])
            if not references or not intervals:
                return {"available": False, "reason": "insufficient_reference_intervals", "exclusions": excluded}
            r_ref, dt = float(np.median(references)), float(np.median(intervals))
            decay = math.exp(-math.log(2) * dt / config.kalman_half_life_seconds)
            gain = -math.expm1(-math.log(2) * dt / config.kalman_half_life_seconds)
            q = r_ref * gain * gain / (decay * dt) if decay > 0 else math.inf
            if not math.isfinite(q) or q <= 0:
                return {"available": False, "reason": "invalid_process_variance", "exclusions": excluded}
            return {"available": True, "symbols": [symbols[j] for j in eligible],
                    "alpha": alpha.tolist(), "r": r.tolist(), "q": q,
                    "r_ref": r_ref, "delta_ref": dt, "distinct_counts": counts.tolist(),
                    "coverage_seconds": mask.sum(axis=0).tolist(), "exclusions": excluded}
    return {"available": False, "reason": "fewer_than_three_calibrated_etfs", "exclusions": excluded}


def filter_grid(grid: Grid, symbols: list[str], fit: dict, config: GoldKalmanRunConfig,
                method: str = "scheduled") -> dict[str, np.ndarray]:
    """Score before update. Market diagnostics remain available while suppressed."""
    t_count, n = grid.valid.shape
    result = {key: np.full((t_count, n), np.nan) for key in
              ("fair", "z", "delta", "benchmark_variance", "persistence")}
    market = np.full((t_count, 6), np.nan)  # factor, sigma, coverage, dispersion, max|z|, ready
    result["market"] = market
    if not fit.get("available"):
        market[:, 2] = 0
        market[:, 5] = 0
        return result
    indices = np.array([symbols.index(s) for s in fit["symbols"]])
    alpha, r = np.array(fit["alpha"]), np.array(fit["r"])
    weight = 1 / r
    valid = grid.valid[:, indices]
    new = grid.new[:, indices] & valid
    with np.errstate(divide="ignore", invalid="ignore"):
        normalized = np.log(grid.micro[:, indices]) - alpha
    factor = variance = initialized_at = previous = None
    persistence = np.zeros(len(indices), dtype=int)
    for t, now in enumerate(grid.times):
        fresh = np.flatnonzero(valid[t])
        coverage = len(fresh)
        market[t, 2] = coverage
        market[t, 5] = 0
        if factor is None:
            if coverage >= 3:
                variance = 1 / weight[fresh].sum()
                factor = variance * np.dot(weight[fresh], normalized[t, fresh])
                initialized_at = previous = now
                market[t, :2] = factor, math.sqrt(variance)
            continue
        prior_var = variance + fit["q"] * (now - previous)
        previous = now
        updates = np.flatnonzero(new[t])
        w = weight[updates].sum()
        b = np.dot(weight[updates], normalized[t, updates])
        ready = coverage >= 3 and now - initialized_at >= config.warmup_seconds
        persistence[~valid[t]] = 0
        if ready:
            own_w = np.where(new[t, fresh], weight[fresh], 0)
            excluded_var = 1 / (1 / prior_var + w - own_w)
            fair_factor = excluded_var * (factor / prior_var + b - own_w * normalized[t, fresh])
            if method == "peer_median":
                fair_factor = peer_medians(normalized[t, fresh])
                # Comparator standardized by the same modeled scale; not a Gaussian probability.
            residual = normalized[t, fresh] - fair_factor
            z = residual / np.sqrt(r[fresh] + excluded_var)
            persistence[fresh] = np.where(np.abs(z) >= config.z_alert, persistence[fresh] + 1, 0)
            target = indices[fresh]
            result["fair"][t, target] = np.exp(alpha[fresh] + fair_factor)
            result["z"][t, target] = z
            result["delta"][t, target] = residual
            result["benchmark_variance"][t, target] = excluded_var
            result["persistence"][t, target] = persistence[fresh]
            market[t, 4:6] = np.max(np.abs(z)), 1
        else:
            persistence[:] = 0
        variance = 1 / (1 / prior_var + w)
        factor = variance * (factor / prior_var + b)
        market[t, :2] = factor, math.sqrt(variance)
        if coverage:
            market[t, 3] = np.sum((normalized[t, fresh] - factor) ** 2 / r[fresh])
    return result


def outcome_arrays(grid: Grid, endpoint: Grid, result: dict, horizon: float, end: float,
                   calibrated: set[str], symbols: list[str]) -> dict:
    """Frozen equal-weight peers, with all required books checked at exact t+H."""
    eligible = np.array([s in calibrated for s in symbols])
    peers = grid.valid & eligible[None, :]
    counts = peers.sum(axis=1)
    future_ok = np.all(~peers | endpoint.valid, axis=1) & (grid.times + horizon < end)
    published = np.isfinite(result["z"])
    available = published & future_ok[:, None] & (counts >= 3)[:, None]
    with np.errstate(divide="ignore", invalid="ignore"):
        returns = np.log(endpoint.mid / grid.mid)
        returns = np.where(peers & endpoint.valid, returns, 0)
        total = returns.sum(axis=1)
        relative = returns - (total[:, None] - returns) / np.maximum(counts[:, None] - 1, 1)
        gap = np.log(grid.mid / result["fair"])
        recovery = -np.sign(result["delta"]) * 10000 * relative
        reduction = 10000 * (np.abs(gap) - np.abs(gap + relative))
        micro_error = np.abs(np.log(endpoint.mid / grid.micro)) * 10000
        mid_error = np.abs(np.log(endpoint.mid / grid.mid)) * 10000
    return {"available": available, "recovery": np.where(available, recovery, np.nan),
            "reduction": np.where(available, reduction, np.nan),
            "relative": np.where(available, relative, np.nan),
            "micro_error": np.where(available, micro_error, np.nan),
            "mid_error": np.where(available, mid_error, np.nan), "peers": peers}
