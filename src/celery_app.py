import os
from celery import Celery
from celery.schedules import crontab

_redis_url = f"redis://{os.getenv('REDIS_HOST', 'redis')}:{os.getenv('REDIS_PORT', '6379')}/0"

celery = Celery(
    "data_collector",
    broker=_redis_url,
)

celery.conf.update(
    task_serializer="pickle",
    accept_content=["pickle", "json"],
    result_serializer="pickle",
    result_backend=_redis_url,
    timezone="Asia/Tehran",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
)

beat_hour = int(os.getenv("BEAT_FETCH_HOUR", "1"))

celery.conf.beat_schedule = {
    "fetch-yesterday-orderbook": {
        "task": "src.tasks.fetch_yesterday_orderbook",
        "schedule": crontab(hour=beat_hour, minute=0),
    },
}

celery.autodiscover_tasks(["src.tasks"])