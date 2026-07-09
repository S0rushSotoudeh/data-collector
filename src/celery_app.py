import os
from celery import Celery
from celery.schedules import crontab

_redis_url = f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}/0"

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
    timezone="Asia/Tehran",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

beat_hour = int(os.getenv("BEAT_FETCH_HOUR", "1"))

celery.conf.beat_schedule = {
    "fetch-yesterday-bond-order-book": {
        "task": "src.tasks.fetch_yesterday_bond_order_book",
        "schedule": crontab(hour=beat_hour, minute=0),
    },
    "fetch-yesterday-bond-trades": {
        "task": "src.tasks.fetch_yesterday_bond_trades",
        "schedule": crontab(hour=beat_hour, minute=5),
    }
}

celery.autodiscover_tasks(["src.tasks"])

# Ensure task modules are imported so @shared_task decorators register
import src.tasks  # noqa: F401
