from __future__ import annotations

import json
import math
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Iterable

from sqlalchemy import func, select

from src.db.models.operations import OperationRun
from src.db.session import SessionLocal


RUN_STATUSES = ("queued", "running", "completed", "failed", "skipped")
PROGRESS_UPDATE_PERCENT = 5


@dataclass(frozen=True)
class TaskSpec:
    family: str
    run_type: str
    target: str


class RunProgressReporter:
    """Accumulate task progress and persist it in coarse, bounded batches."""

    def __init__(self, run_id: str | uuid.UUID | None, *, percent_step: int = PROGRESS_UPDATE_PERCENT) -> None:
        self.run_id = run_id
        self.percent_step = max(1, min(100, int(percent_step)))
        self.total = 0
        self.current = 0
        self.output_count = 0
        self.warning_count = 0
        self._last_persisted = 0

    def set_total(self, total: int) -> None:
        self.total = max(0, int(total))
        if self.run_id:
            update_progress(
                self.run_id,
                current=self.current,
                total=self.total,
                output_count=self.output_count,
                warning_count=self.warning_count,
            )

    def advance(self, *, output_count: int = 0, warning_count: int = 0) -> None:
        self.current += 1
        self.output_count += max(0, int(output_count))
        self.warning_count += max(0, int(warning_count))
        self.checkpoint(
            self.current,
            output_count=self.output_count,
            warning_count=self.warning_count,
        )

    def checkpoint(
        self,
        current: int,
        *,
        total: int | None = None,
        output_count: int | None = None,
        warning_count: int | None = None,
        result: dict[str, Any] | None = None,
        force: bool = False,
    ) -> None:
        """Persist an absolute progress position at the configured interval."""
        if total is not None:
            self.total = max(0, int(total))
        self.current = max(self.current, max(0, int(current)))
        if output_count is not None:
            self.output_count = max(0, int(output_count))
        if warning_count is not None:
            self.warning_count = max(0, int(warning_count))
        if not self.run_id or not self.total:
            return
        batch_size = max(1, math.ceil(self.total * self.percent_step / 100))
        if not force and self.current < self.total and self.current - self._last_persisted < batch_size:
            return
        update_progress(
            self.run_id,
            current=min(self.current, self.total),
            total=self.total,
            output_count=self.output_count,
            warning_count=self.warning_count,
            result=result,
        )
        self._last_persisted = self.current


TASK_SPECS: dict[str, TaskSpec] = {
    "src.tasks.sync_bond_instruments": TaskSpec("collection", "collection.sync_bond_instruments", "bond_instruments"),
    "src.tasks.sync_option_instruments": TaskSpec("collection", "collection.sync_option_instruments", "option_instruments"),
    "src.tasks.sync_stock_instruments": TaskSpec("collection", "collection.sync_stock_instruments", "stock_instruments"),
    "src.tasks.fetch_yesterday_bond_order_book": TaskSpec("collection", "collection.daily_bond_order_book", "bond_order_book"),
    "src.tasks.fetch_yesterday_bond_trades": TaskSpec("collection", "collection.daily_bond_trades", "bond_trades"),
    "src.tasks.fetch_yesterday_option_orderbook": TaskSpec("collection", "collection.daily_option_order_book", "option_order_book"),
    "src.tasks.fetch_yesterday_option_trades": TaskSpec("collection", "collection.daily_option_trades", "option_trades"),
    "src.tasks.fetch_yesterday_stock_orderbook": TaskSpec("collection", "collection.daily_stock_order_book", "stock_order_book"),
    "src.tasks.fetch_yesterday_stock_trades": TaskSpec("collection", "collection.daily_stock_trades", "stock_trades"),
    "src.tasks.fetch_yesterday_gold_orderbook": TaskSpec("collection", "collection.daily_gold_order_book", "gold_order_book"),
    "src.tasks.fetch_yesterday_gold_trades": TaskSpec("collection", "collection.daily_gold_trades", "gold_trades"),
    "src.tasks.backfill_bond_order_books_task": TaskSpec("collection", "collection.backfill_bond_order_book", "bond_order_book"),
    "src.tasks.backfill_bond_trades_task": TaskSpec("collection", "collection.backfill_bond_trades", "bond_trades"),
    "src.tasks.backfill_option_order_books_task": TaskSpec("collection", "collection.backfill_option_order_book", "option_order_book"),
    "src.tasks.backfill_option_trades_task": TaskSpec("collection", "collection.backfill_option_trades", "option_trades"),
    "src.tasks.backfill_stock_order_books_task": TaskSpec("collection", "collection.backfill_stock_order_book", "stock_order_book"),
    "src.tasks.backfill_stock_trades_task": TaskSpec("collection", "collection.backfill_stock_trades", "stock_trades"),
    "src.tasks.backfill_gold_order_books_task": TaskSpec("collection", "collection.backfill_gold_order_book", "gold_order_book"),
    "src.tasks.backfill_gold_trades_task": TaskSpec("collection", "collection.backfill_gold_trades", "gold_trades"),
    "src.tasks.sync_ime_producers": TaskSpec("collection", "collection.sync_ime_producers", "ime_producers"),
    "src.tasks.backfill_ime_physical_trades": TaskSpec("collection", "collection.backfill_ime_physical_trades", "ime_physical_trades"),
    "src.tasks.fetch_recent_ime_physical_trades": TaskSpec("collection", "collection.daily_ime_physical_trades", "ime_physical_trades"),
    "src.tasks.compute_yield_curve_snapshot": TaskSpec("yield_curve", "yield_curve.snapshot", "yield_curve"),
    "src.tasks.backfill_yield_curves": TaskSpec("yield_curve", "yield_curve.backfill", "yield_curve"),
    "src.tasks.compute_option_market_potential_daily": TaskSpec("market_potential", "market_potential.daily", "option_market_potential"),
    "src.tasks.run_parity_analysis": TaskSpec("parity", "parity.analysis", "put_call_parity"),
    "src.tasks.run_box_spread_analysis": TaskSpec("box_spread", "box_spread.analysis", "box_spread"),
    "src.tasks.run_iv_surface": TaskSpec("iv_orc", "iv_orc.surface", "iv_surface_orc_wing"),
    "src.tasks.run_option_mispricing": TaskSpec("option_mispricing", "option_mispricing.market_scan", "market_wide"),
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _jsonable(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    return str(value)


def _as_date(value: Any) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None
    return None


def create_run(
    *,
    family: str,
    run_type: str,
    target: str | None = None,
    trigger: str = "manual",
    config: dict[str, Any] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    created_by: str | None = None,
    progress_total: int = 0,
    run_id: str | uuid.UUID | None = None,
    created_at: datetime | None = None,
    updated_at: datetime | None = None,
) -> OperationRun:
    identifier = uuid.UUID(str(run_id)) if run_id else uuid.uuid4()
    with SessionLocal() as session:
        existing = session.get(OperationRun, identifier)
        if existing is not None:
            return existing
        row = OperationRun(
            run_id=identifier,
            family=family,
            run_type=run_type,
            target=target,
            trigger=trigger,
            config=_jsonable(config or {}),
            start_date=start_date,
            end_date=end_date,
            created_by=created_by,
            progress_total=max(0, int(progress_total or 0)),
            created_at=created_at,
            updated_at=updated_at,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def get_run(run_id: str | uuid.UUID) -> OperationRun | None:
    try:
        identifier = uuid.UUID(str(run_id))
    except (TypeError, ValueError):
        return None
    with SessionLocal() as session:
        row = session.get(OperationRun, identifier)
        if row is not None:
            session.expunge(row)
        return row


def get_run_by_task_id(task_id: str) -> OperationRun | None:
    with SessionLocal() as session:
        row = session.scalar(select(OperationRun).where(OperationRun.celery_task_id == task_id))
        if row is not None:
            session.expunge(row)
        return row


def update_run(run_id: str | uuid.UUID, **values: Any) -> OperationRun | None:
    try:
        identifier = uuid.UUID(str(run_id))
    except (TypeError, ValueError):
        return None
    with SessionLocal() as session:
        row = session.get(OperationRun, identifier)
        if row is None:
            return None
        now = _utcnow()
        status = values.pop("status", None)
        if status:
            if status not in RUN_STATUSES:
                raise ValueError(f"unsupported operation status: {status}")
            row.status = status
            if status == "running" and row.started_at is None:
                row.started_at = now
            if status in {"completed", "failed", "skipped"}:
                row.completed_at = now
        for name, value in values.items():
            if name in {"config", "result"}:
                value = _jsonable(value or {})
            if hasattr(row, name) and value is not None:
                setattr(row, name, value)
        row.updated_at = now
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
        return row


def update_progress(
    run_id: str | uuid.UUID,
    *,
    current: int | None = None,
    total: int | None = None,
    output_count: int | None = None,
    warning_count: int | None = None,
    result: dict[str, Any] | None = None,
) -> OperationRun | None:
    values: dict[str, Any] = {"status": "running"}
    if current is not None:
        values["progress_current"] = max(0, int(current))
    if total is not None:
        values["progress_total"] = max(0, int(total))
    if output_count is not None:
        values["output_count"] = max(0, int(output_count))
    if warning_count is not None:
        values["warning_count"] = max(0, int(warning_count))
    if result is not None:
        values["result"] = result
    return update_run(run_id, **values)


def _message_config(args: Iterable[Any], kwargs: dict[str, Any]) -> tuple[dict[str, Any], date | None, date | None]:
    args_list = list(args)
    config = {"args": _jsonable(args_list), **_jsonable(kwargs)}
    start = _as_date(kwargs.get("start_date_str") or kwargs.get("start_date"))
    end = _as_date(kwargs.get("end_date_str") or kwargs.get("end_date"))
    day = _as_date(kwargs.get("day_str"))
    if day:
        start = end = day
    return config, start, end


def create_for_task_message(
    task_name: str,
    task_id: str,
    args: Iterable[Any],
    kwargs: dict[str, Any],
    *,
    trigger: str = "scheduled",
) -> OperationRun | None:
    spec = TASK_SPECS.get(task_name)
    if spec is None:
        return None
    config, start, end = _message_config(args, kwargs)
    row = create_run(
        family=spec.family,
        run_type=spec.run_type,
        target=spec.target,
        trigger=trigger,
        config=config,
        start_date=start,
        end_date=end,
    )
    return update_run(row.run_id, celery_task_id=task_id)


def enqueue_task(
    task: Any,
    *,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
    trigger: str = "manual",
    created_by: str | None = None,
    family: str | None = None,
    run_type: str | None = None,
    target: str | None = None,
    config: dict[str, Any] | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    progress_total: int = 0,
    run_id: str | uuid.UUID | None = None,
) -> tuple[OperationRun, Any]:
    spec = TASK_SPECS.get(task.name)
    if spec is None and not (family and run_type):
        raise ValueError(f"task is not registered for operation tracking: {task.name}")
    task_args = args or []
    task_kwargs = kwargs or {}
    derived_config, derived_start, derived_end = _message_config(task_args, task_kwargs)
    row = create_run(
        family=family or spec.family,
        run_type=run_type or spec.run_type,
        target=target or spec.target,
        trigger=trigger,
        created_by=created_by,
        config=config if config is not None else derived_config,
        start_date=start_date or derived_start,
        end_date=end_date or derived_end,
        progress_total=progress_total,
        run_id=run_id,
    )
    try:
        result = task.apply_async(
            args=task_args,
            kwargs=task_kwargs,
            headers={"operation_run_id": str(row.run_id), "operation_trigger": trigger},
        )
    except Exception as exc:
        update_run(row.run_id, status="failed", error=str(exc)[:4000])
        raise
    row = update_run(row.run_id, celery_task_id=result.id) or row
    return row, result


def _result_count(result: dict[str, Any]) -> int:
    for key in ("point_count", "snapshot_count", "total_rows", "rows", "inserted", "synced", "dates_processed"):
        value = result.get(key)
        if isinstance(value, (int, float)):
            return max(0, int(value))
    return 0


def finish_run(run_id: str | uuid.UUID, result: Any) -> OperationRun | None:
    payload = result if isinstance(result, dict) else {"value": _jsonable(result)}
    status = "skipped" if payload.get("status") == "skipped" else "completed"
    warning_count = payload.get("warning_count", 0)
    if not warning_count and isinstance(payload.get("errors"), list):
        warning_count = len(payload["errors"])
    row = get_run(run_id)
    current = row.progress_total if row and row.progress_total else row.progress_current if row else 0
    return update_run(
        run_id,
        status=status,
        result=payload,
        progress_current=current,
        output_count=_result_count(payload),
        warning_count=max(0, int(warning_count or 0)),
        error="",
    )


def fail_run(run_id: str | uuid.UUID, error: Any) -> OperationRun | None:
    return update_run(run_id, status="failed", error=str(error)[:4000])


def list_runs(
    *,
    family: str | None = None,
    run_type: str | None = None,
    status: str | None = None,
    run_id: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    offset: int = 0,
    limit: int = 100,
) -> tuple[int, list[OperationRun]]:
    clauses = []
    if family:
        clauses.append(OperationRun.family == family)
    if run_type:
        clauses.append(OperationRun.run_type == run_type)
    if status:
        clauses.append(OperationRun.status == status)
    if run_id:
        try:
            clauses.append(OperationRun.run_id == uuid.UUID(run_id))
        except ValueError:
            return 0, []
    if start_date:
        clauses.append(OperationRun.created_at >= datetime.combine(start_date, datetime.min.time(), timezone.utc))
    if end_date:
        clauses.append(OperationRun.created_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time(), timezone.utc))
    with SessionLocal() as session:
        total = int(session.scalar(select(func.count()).select_from(OperationRun).where(*clauses)) or 0)
        rows = session.execute(
            select(OperationRun).where(*clauses).order_by(OperationRun.created_at.desc()).offset(offset).limit(limit)
        ).scalars().all()
        for row in rows:
            session.expunge(row)
        return total, rows


def run_to_dict(row: OperationRun) -> dict[str, Any]:
    merged = dict(row.config or {})
    merged.update(row.result or {})
    merged.update({
        "run_id": str(row.run_id), "family": row.family, "run_type": row.run_type,
        "status": row.status, "trigger": row.trigger, "task_id": row.celery_task_id,
        "target": row.target, "start_date": row.start_date, "end_date": row.end_date,
        "progress_current": row.progress_current, "progress_total": row.progress_total,
        "output_count": row.output_count, "warning_count": row.warning_count,
        "error": row.error or "", "created_by": row.created_by,
        "created_at": row.created_at, "started_at": row.started_at,
        "completed_at": row.completed_at, "updated_at": row.updated_at,
        "config": row.config or {}, "result": row.result or {},
    })
    return merged


def import_legacy_clickhouse_runs() -> dict[str, int]:
    """Idempotently copy legacy parity/IV lifecycle rows into PostgreSQL."""
    from src.db.clickhouse import get_client

    client = get_client()
    imported = {"parity": 0, "iv_orc": 0}
    definitions = (
        ("parity_analysis_runs", "parity", "parity.analysis", "put_call_parity"),
        ("iv_surface_runs", "iv_orc", "iv_orc.surface", "iv_surface_orc_wing"),
    )
    for table, family, run_type, target in definitions:
        result = client.query(f"SELECT * FROM `{table}` FINAL")
        for values in result.result_rows:
            raw = dict(zip(result.column_names, values))
            existing = get_run(str(raw["run_id"]))
            if existing is not None:
                if existing.trigger == "legacy" and not existing.progress_total:
                    update_run(
                        existing.run_id,
                        progress_total=int(
                            raw.get("target_snapshot_count", 0)
                            or raw.get("completed_snapshot_count", 0)
                            or raw.get("snapshot_count", 0)
                            or 0
                        ),
                    )
                continue
            try:
                parsed = json.loads(raw.get("config_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                parsed = {}
            config = _jsonable(raw) | _jsonable(parsed)
            row = create_run(
                family=family, run_type=run_type, target=raw.get("underlying_instrument_code") or target,
                trigger="legacy", config=config, start_date=raw.get("start_date"), end_date=raw.get("end_date"),
                run_id=str(raw["run_id"]), created_at=raw.get("created_at"), updated_at=raw.get("updated_at"),
                progress_total=int(raw.get("target_snapshot_count", 0) or 0),
            )
            counts = {
                key: int(raw.get(key, 0) or 0) for key in (
                    "snapshot_count", "valid_count", "invalid_count", "opportunity_count",
                    "completed_snapshot_count", "point_count", "fit_count", "warning_count",
                )
            }
            status = str(raw.get("status") or "queued").lower()
            if status not in RUN_STATUSES:
                status = "completed" if status in {"success", "succeeded"} else "failed" if status == "failure" else "queued"
            update_run(
                row.run_id, status=status, result=counts,
                progress_current=counts.get("completed_snapshot_count") or counts.get("snapshot_count") or 0,
                progress_total=(
                    int(raw.get("target_snapshot_count", 0) or 0)
                    or counts.get("completed_snapshot_count")
                    or counts.get("snapshot_count")
                    or 0
                ),
                output_count=counts.get("point_count") or counts.get("snapshot_count") or 0,
                warning_count=counts.get("warning_count") or 0, error=str(raw.get("error") or "")[:4000],
            )
            imported[family] += 1
    return imported
