from __future__ import annotations

import csv
import hashlib
import io
import math
import uuid
from datetime import datetime
from functools import lru_cache

import numpy as np
import clickhouse_connect
from sqlalchemy import select

from src.analytics.gold_consensus import canonical_events
from src.analytics.gold_consensus_config import DatasetManifest
from src.config import env, env_int
from src.db.models.gold_consensus import GoldKalmanDataset
from src.db.session import SessionLocal

INPUT_COLUMNS = ["dataset_id", "session_index", "instrument_code", "available_at", "quote_time", "sequence", "bid", "ask", "bid_qty", "ask_qty", "phase"]
COMMON = ["run_id", "method", "range_name", "decision_time", "calibration_id"]
COLUMNS = {
    "scores": COMMON + ["instrument_code", "microprice", "midpoint", "bid", "ask", "fair_price", "z_score", "residual", "benchmark_variance", "mispricing_bps", "cheap_edge_bps", "rich_edge_bps", "spread_bps", "imbalance", "quote_age", "coverage", "persistence", "alert"],
    "market": COMMON + ["factor", "factor_sigma", "coverage", "dispersion", "max_abs_z", "ready", "reason", "symbols", "midpoints"],
    "outcomes": COMMON + ["instrument_code", "horizon", "available", "reason", "relative_return", "recovery_log_bps", "gap_reduction_log_bps", "micro_error_log_bps", "mid_error_log_bps"],
}
CSV_COLUMNS = ["symbol", "available_at", "quote_time", "sequence", "bid", "ask", "bid_qty", "ask_qty", "phase"]


@lru_cache(maxsize=1)
def get_client():
    # Independent HTTP queries may overlap (chart, status and streamed export).
    # A shared server-side session would reject that concurrency.
    return clickhouse_connect.get_client(host=env("CLICKHOUSE_HOST"), port=env_int("CLICKHOUSE_PORT"),
        username=env("CLICKHOUSE_USER"), password=env("CLICKHOUSE_PASSWORD"), autogenerate_session_id=False)


def dataset_row(dataset_id):
    with SessionLocal() as session:
        return session.get(GoldKalmanDataset, uuid.UUID(str(dataset_id)))


def list_datasets():
    with SessionLocal() as session:
        rows = session.execute(select(GoldKalmanDataset).order_by(GoldKalmanDataset.created_at.desc()).limit(100)).scalars().all()
        return [{"dataset_id": str(r.dataset_id), "name": r.name, "status": r.status,
                 "row_count": r.row_count, "sha256": r.sha256, "manifest": r.manifest, "error": r.error} for r in rows]


def parse_instant(value):
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("CSV timestamps must include their timezone")
    return stamp.timestamp()


def import_dataset(manifest: DatasetManifest, binary_file) -> dict:
    """Append once, then publish ready metadata. Failed uploads stay unavailable."""
    dataset = GoldKalmanDataset(name=manifest.name, manifest=manifest.model_dump(mode="json"))
    with SessionLocal() as session:
        session.add(dataset)
        session.commit()
        session.refresh(dataset)
    dataset_id = dataset.dataset_id
    count = 0
    digest = hashlib.sha256()
    client = get_client()
    bounds = [(s.open.timestamp(), s.close.timestamp(), set(s.eligible_symbols)) for s in manifest.sessions]
    starts = np.array([x[0] for x in bounds])
    wrapper = io.TextIOWrapper(binary_file, encoding="utf-8-sig", newline="")
    try:
        reader = csv.DictReader(wrapper)
        if reader.fieldnames != CSV_COLUMNS:
            raise ValueError("CSV columns must be: " + ",".join(CSV_COLUMNS))
        batch = []
        for line, record in enumerate(reader, 2):
            available, quote = parse_instant(record["available_at"]), parse_instant(record["quote_time"])
            index = int(np.searchsorted(starts, available, side="right") - 1)
            if index < 0 or available >= bounds[index][1] or quote < bounds[index][0] or quote > available:
                raise ValueError(f"line {line}: event outside its declared session or future quote")
            symbol = record["symbol"]
            if symbol not in bounds[index][2]:
                raise ValueError(f"line {line}: symbol absent from historical eligibility manifest")
            sequence = int(record["sequence"])
            if not 0 <= sequence <= 2**53:
                raise ValueError(f"line {line}: sequence out of range")
            prices = [float(record[k]) for k in ("bid", "ask", "bid_qty", "ask_qty")]
            if not all(math.isfinite(v) for v in prices):
                raise ValueError(f"line {line}: nonfinite book")
            if record["phase"] not in {"continuous", "auction", "halted", "unknown"}:
                raise ValueError(f"line {line}: unknown phase label")
            phase = {"unknown": 0, "continuous": 1, "auction": 2, "halted": 3}[record["phase"]]
            row = [dataset_id, index, symbol, available, quote, sequence, *prices, phase]
            digest.update((repr(row[1:]) + "\n").encode())
            batch.append(row)
            count += 1
            if len(batch) >= 25000:
                client.insert("gold_kalman_inputs", batch, column_names=INPUT_COLUMNS)
                batch.clear()
        if batch:
            client.insert("gold_kalman_inputs", batch, column_names=INPUT_COLUMNS)
        # Verify event identity/order before making the frozen dataset usable.
        for index in range(len(bounds)):
            load_events(dataset_id, index, client)
        with SessionLocal() as session:
            row = session.get(GoldKalmanDataset, dataset_id)
            row.status, row.sha256, row.row_count = "ready", digest.hexdigest(), count
            session.add(row)
            session.commit()
        return {"dataset_id": str(dataset_id), "status": "ready", "row_count": count, "sha256": digest.hexdigest()}
    except Exception as exc:
        with SessionLocal() as session:
            row = session.get(GoldKalmanDataset, dataset_id)
            row.status, row.error, row.row_count = "failed", str(exc)[:2000], count
            session.add(row)
            session.commit()
        raise
    finally:
        wrapper.detach()


def load_events(dataset_id, index, client=None):
    client = client or get_client()
    rows = client.query("SELECT instrument_code, available_at, quote_time, sequence, bid, ask, bid_qty, ask_qty, phase "
                        "FROM gold_kalman_inputs WHERE dataset_id={id:UUID} AND session_index={index:UInt16} "
                        "ORDER BY instrument_code, available_at, sequence",
                        parameters={"id": str(dataset_id), "index": index}).result_rows
    grouped = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(row[1:])
    return {symbol: canonical_events(np.array(values)) for symbol, values in grouped.items()}


def insert_rows(client, kind, rows):
    if rows:
        client.insert("gold_kalman_" + kind, rows, column_names=COLUMNS[kind])


def query_rows(kind, run_id, *, method="scheduled", decision_time=None, symbol=None,
               limit=1000, offset=0, start=None, end=None, compact=False):
    if kind not in COLUMNS:
        raise ValueError("unknown output kind")
    where = "run_id={id:UUID} AND method={method:String}"
    params = {"id": str(run_id), "method": method, "limit": limit, "offset": offset}
    for field, value, operator in (("decision_time", decision_time, "="), ("decision_time", start, ">="), ("decision_time", end, "<")):
        if value is not None:
            key = {"=": "time", ">=": "start", "<": "end"}[operator]
            where += f" AND {field}{operator}{{{key}:DateTime64(3)}}"
            params[key] = value
    if symbol is not None and kind != "market":
        where += " AND instrument_code={symbol:String}"
        params["symbol"] = symbol
    columns = COLUMNS[kind][:-2] if kind == "market" and compact else COLUMNS[kind]
    sql = f"SELECT {', '.join(columns)} FROM gold_kalman_{kind} FINAL WHERE {where} ORDER BY decision_time"
    if kind != "market":
        sql += ", instrument_code"
    result = get_client().query(sql + " LIMIT {limit:UInt32} OFFSET {offset:UInt64}", parameters=params)
    return [dict(zip(columns, r)) for r in result.result_rows]


def stream_csv(kind, run_id, method):
    if kind not in COLUMNS:
        raise ValueError("unknown output kind")
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(COLUMNS[kind])
    yield buffer.getvalue()
    with get_client().query_row_block_stream(
        f"SELECT {', '.join(COLUMNS[kind])} FROM gold_kalman_{kind} FINAL "
        "WHERE run_id={id:UUID} AND method={method:String} ORDER BY decision_time",
        parameters={"id": str(run_id), "method": method}) as stream:
        for block in stream:
            buffer.seek(0)
            buffer.truncate()
            writer.writerows(block)
            yield buffer.getvalue()
