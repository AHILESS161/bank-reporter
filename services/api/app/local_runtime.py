from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .config import get_settings


@dataclass(frozen=True)
class LocalTaskHandle:
    id: str


_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="bank-reporter")
_stop = threading.Event()
_scheduler_thread: threading.Thread | None = None


def dispatch_task(task: Any, *args: Any) -> Any:
    """Send a Celery task to Redis or execute its task body in the desktop pool."""
    if get_settings().task_backend.casefold() != "local":
        return task.delay(*args)
    handle = LocalTaskHandle(id=str(uuid.uuid4()))
    _executor.submit(task.run, *args)
    return handle


def _schedule_loop() -> None:
    from .tasks import (
        forecast_calendar,
        monitor_expected_publications,
        sync_calendar,
        sync_key_rate_publication,
        telegram_commands,
        telegram_digest,
        telegram_reminders,
    )

    completed_slots: set[str] = set()
    timezone = ZoneInfo(get_settings().app_timezone)
    while not _stop.wait(20):
        now = datetime.now(timezone)
        minute_slot = now.strftime("%Y-%m-%d-%H-%M")
        hour_slot = now.strftime("%Y-%m-%d-%H")
        day_slot = now.strftime("%Y-%m-%d")
        jobs: list[tuple[str, Any]] = [(f"commands-{minute_slot}", telegram_commands)]
        if now.minute == 0:
            jobs.append((f"reminders-{hour_slot}", telegram_reminders))
        if now.hour == 6 and now.minute < 20:
            jobs.append((f"calendar-{day_slot}", sync_calendar))
        if now.hour == 6 and 20 <= now.minute < 40:
            jobs.append((f"forecast-{day_slot}", forecast_calendar))
        if now.hour == 8 and now.minute < 20:
            jobs.append((f"digest-{day_slot}", telegram_digest))
        if 8 <= now.hour <= 20 and now.minute in range(0, 20):
            jobs.extend(
                [
                    (f"key-rate-{hour_slot}-0", sync_key_rate_publication),
                    (f"expected-{hour_slot}-0", monitor_expected_publications),
                ]
            )
        if 8 <= now.hour <= 20 and now.minute in range(30, 50):
            jobs.extend(
                [
                    (f"key-rate-{hour_slot}-30", sync_key_rate_publication),
                    (f"expected-{hour_slot}-30", monitor_expected_publications),
                ]
            )
        for key, task in jobs:
            if key not in completed_slots:
                completed_slots.add(key)
                dispatch_task(task)
        if len(completed_slots) > 500:
            completed_slots = {key for key in completed_slots if day_slot in key}


def start_local_scheduler() -> None:
    global _scheduler_thread
    if get_settings().task_backend.casefold() != "local":
        return
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _stop.clear()
    _scheduler_thread = threading.Thread(
        target=_schedule_loop, name="bank-reporter-scheduler", daemon=True
    )
    _scheduler_thread.start()


def stop_local_scheduler() -> None:
    _stop.set()
