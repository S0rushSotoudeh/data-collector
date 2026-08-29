from celery import Celery
import os
from celery.signals import before_task_publish, task_failure, task_postrun, task_prerun
from celery.schedules import crontab

from src.config import env, env_int

from src.services.operation_runs import (
    TASK_SPECS,
    create_for_task_message,
    fail_run,
    finish_run,
    update_run,
)

_redis_url = env("REDIS_URL")

celery = Celery(
    "data_collector",
    broker=_redis_url,
    backend=_redis_url,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_backend=_redis_url,
    timezone=env("APP_TIMEZONE"),
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

beat_hour = env_int("BEAT_FETCH_HOUR")

celery.conf.beat_schedule = {
    "fetch-yesterday-bond-order-book": {
        "task": "src.tasks.fetch_yesterday_bond_order_book",
        "schedule": crontab(
            hour=beat_hour, minute=env_int("BEAT_BOND_ORDER_BOOK_MINUTE")
        ),
    },
    "fetch-yesterday-bond-trades": {
        "task": "src.tasks.fetch_yesterday_bond_trades",
        "schedule": crontab(
            hour=beat_hour, minute=env_int("BEAT_BOND_TRADES_MINUTE")
        ),
    },
    "sync-option-instruments": {
        "task": "src.tasks.sync_option_instruments",
        "schedule": crontab(
            hour=beat_hour, minute=env_int("BEAT_OPTION_SYNC_MINUTE")
        ),
    },
    "sync-stock-instruments": {
        "task": "src.tasks.sync_stock_instruments",
        "schedule": crontab(
            hour=beat_hour, minute=env_int("BEAT_STOCK_SYNC_MINUTE")
        ),
    },
    "sync-gold-instruments": {
        "task": "src.tasks.sync_gold_instruments",
        "schedule": crontab(
            hour=beat_hour, minute=int(os.environ.get("BEAT_GOLD_SYNC_MINUTE", "15"))
        ),
    },
    "fetch-yesterday-gold-order-book": {
        "task": "src.tasks.fetch_yesterday_gold_order_book",
        "schedule": crontab(
            hour=beat_hour, minute=int(os.environ.get("BEAT_GOLD_ORDER_BOOK_MINUTE", "25"))
        ),
    },
    "fetch-yesterday-gold-trades": {
        "task": "src.tasks.fetch_yesterday_gold_trades",
        "schedule": crontab(
            hour=beat_hour, minute=int(os.environ.get("BEAT_GOLD_TRADES_MINUTE", "35"))
        ),
    },
    "fetch-yesterday-option-order-book": {
        "task": "src.tasks.fetch_yesterday_option_orderbook",
        "schedule": crontab(
            hour=beat_hour, minute=env_int("BEAT_OPTION_ORDER_BOOK_MINUTE")
        ),
    },
    "fetch-yesterday-option-trades": {
        "task": "src.tasks.fetch_yesterday_option_trades",
        "schedule": crontab(
            hour=beat_hour, minute=env_int("BEAT_OPTION_TRADES_MINUTE")
        ),
    },
    "fetch-yesterday-stock-order-book": {
        "task": "src.tasks.fetch_yesterday_stock_orderbook",
        "schedule": crontab(
            hour=beat_hour, minute=env_int("BEAT_STOCK_ORDER_BOOK_MINUTE")
        ),
    },
    "fetch-yesterday-stock-trades": {
        "task": "src.tasks.fetch_yesterday_stock_trades",
        "schedule": crontab(
            hour=beat_hour, minute=env_int("BEAT_STOCK_TRADES_MINUTE")
        ),
    },
    "fetch-recent-ime-physical-trades": {
        "task": "src.tasks.fetch_recent_ime_physical_trades",
        "schedule": crontab(
            hour=beat_hour, minute=int(os.environ.get("BEAT_IME_TRADES_MINUTE", "40"))
        ),
    },
    "compute-yesterday-option-market-potential": {
        "task": "src.tasks.compute_option_market_potential_daily",
        "schedule": crontab(
            hour=beat_hour, minute=env_int("BEAT_MARKET_POTENTIAL_MINUTE")
        ),
    },
}

celery.autodiscover_tasks(["src.tasks"])


def _operation_run_id(task) -> str | None:
    headers = getattr(task.request, "headers", None) or {}
    value = headers.get("operation_run_id")
    return str(value) if value else None


@before_task_publish.connect
def create_scheduled_operation_run(sender=None, body=None, headers=None, **_kwargs):
    """Create queued lifecycle rows for Celery Beat and other direct publishers."""
    if sender not in TASK_SPECS or headers is None or headers.get("operation_run_id"):
        return
    args = body[0] if isinstance(body, (tuple, list)) and len(body) > 0 else []
    kwargs = body[1] if isinstance(body, (tuple, list)) and len(body) > 1 else {}
    row = create_for_task_message(str(sender), str(headers.get("id")), args or [], kwargs or {})
    if row is not None:
        headers["operation_run_id"] = str(row.run_id)
        headers["operation_trigger"] = "scheduled"


@task_prerun.connect
def start_operation_run(sender=None, task=None, **_kwargs):
    current_task = task or sender
    run_id = _operation_run_id(current_task) if current_task is not None else None
    if run_id:
        update_run(run_id, status="running", celery_task_id=current_task.request.id, error="")


@task_postrun.connect
def complete_operation_run(sender=None, task=None, retval=None, state=None, **_kwargs):
    current_task = task or sender
    run_id = _operation_run_id(current_task) if current_task is not None else None
    if run_id and state == "SUCCESS":
        finish_run(run_id, retval)


@task_failure.connect
def fail_operation_run(sender=None, task=None, exception=None, **_kwargs):
    current_task = task or sender
    run_id = _operation_run_id(current_task) if current_task is not None else None
    if run_id:
        fail_run(run_id, exception)

# Ensure task modules are imported so @shared_task decorators register
import src.tasks  # noqa: F401
