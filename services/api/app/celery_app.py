from celery import Celery
from celery.schedules import crontab

from .config import get_settings

settings = get_settings()
celery = Celery("bank_reporter", broker=settings.redis_url, backend=settings.redis_url, include=["app.tasks"])
celery.conf.update(
    timezone=settings.app_timezone,
    enable_utc=True,
    task_track_started=True,
    task_time_limit=15 * 60,
    task_soft_time_limit=14 * 60,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    beat_schedule={
        "sync-editorial-calendar": {"task": "calendar.sync", "schedule": crontab(hour=6, minute=0)},
        "forecast-watchlist": {"task": "calendar.forecast", "schedule": crontab(hour=6, minute=20)},
        "telegram-digest": {"task": "telegram.digest", "schedule": crontab(hour=8, minute=0)},
        "telegram-reminders": {"task": "telegram.reminders", "schedule": crontab(minute=0)},
        "telegram-commands": {"task": "telegram.commands", "schedule": crontab(minute="*")},
        "watch-expected-publications": {
            "task": "calendar.monitor_expected",
            "schedule": crontab(minute="*/30"),
        },
    },
)
