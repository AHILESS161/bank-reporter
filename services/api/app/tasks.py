from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from .config import get_settings

if get_settings().task_backend.casefold() == "local":
    from .local_task import LocalTaskRegistry

    celery = LocalTaskRegistry()

    class SoftTimeLimitExceeded(Exception):
        pass
else:
    from celery.exceptions import SoftTimeLimitExceeded

    from .celery_app import celery
from .db import SessionLocal, create_schema
from .models import AnalysisRun, CalendarEvent, Report
from .services.agent import AgentService
from .services.calendar import CalendarService, upcoming
from .services.documents import DocumentService
from .services.reporting import ReportService
from .services.telegram import TelegramNotifier


@celery.task(name="agent.run", bind=True, autoretry_for=(ConnectionError,), retry_backoff=True, max_retries=2)
def run_agent(self, run_id: str):
    create_schema()
    with SessionLocal() as db:
        try:
            return AgentService(db, run_id).execute()
        except SoftTimeLimitExceeded:
            run = db.get(AnalysisRun, run_id)
            if run:
                run.status = "failed"
                run.error = "Превышен лимит времени"
                db.commit()
            raise
        except Exception as exc:
            run = db.get(AnalysisRun, run_id)
            if run:
                run.status = "failed"
                run.error = str(exc)[:3000]
                from .models import RunEvent

                db.add(RunEvent(run_id=run_id, type="failed", payload={"error": str(exc)}))
                db.commit()
            raise


@celery.task(name="report.create")
def create_report(report_id: str, question: str, output_formats: list[str]):
    create_schema()
    with SessionLocal() as db:
        report = db.get(Report, report_id)
        if not report:
            return None
        report.status = "processing"
        db.commit()
        try:
            documents = DocumentService(db)
            for document_id in report.document_ids:
                documents.reprocess(document_id)
            return ReportService(db, report.analysis_run_id).create(report, question, output_formats).id
        except Exception as exc:
            db.rollback()
            report = db.get(Report, report_id)
            if report:
                report.status = "failed"
                report.summary = f"Не удалось обработать исходный документ: {exc}"
                db.commit()
            raise


@celery.task(name="calendar.sync")
def sync_calendar():
    create_schema()
    with SessionLocal() as db:
        return CalendarService(db).sync_cbr()


@celery.task(name="calendar.forecast")
def forecast_calendar():
    create_schema()
    with SessionLocal() as db:
        return CalendarService(db).forecast_watchlist()


@celery.task(name="calendar.sync_key_rate")
def sync_key_rate_publication():
    create_schema()
    with SessionLocal() as db:
        return CalendarService(db).sync_key_rate_publication()


@celery.task(name="calendar.monitor_expected")
def monitor_expected_publications():
    create_schema()
    with SessionLocal() as db:
        return CalendarService(db).monitor_expected_publications()


@celery.task(name="telegram.digest")
def telegram_digest():
    create_schema()
    with SessionLocal() as db:
        return TelegramNotifier().digest(upcoming(db, 7))


@celery.task(name="telegram.reminders")
def telegram_reminders():
    create_schema()
    notifier = TelegramNotifier()
    if not notifier.configured:
        return 0
    now = datetime.now(timezone.utc)
    until = now + timedelta(hours=25)
    count = 0
    with SessionLocal() as db:
        events = db.scalars(
            select(CalendarEvent).where(
                CalendarEvent.starts_at >= now + timedelta(hours=23),
                CalendarEvent.starts_at <= until,
                CalendarEvent.notified_24h.is_(False),
            )
        ).all()
        for item in events:
            if notifier.send(
                f"Через сутки: {item.title}\n{item.starts_at.astimezone():%d.%m.%Y %H:%M}\n{item.source_url or ''}"
            ):
                item.notified_24h = True
                count += 1
        db.commit()
    return count


@celery.task(name="telegram.commands")
def telegram_commands():
    create_schema()
    with SessionLocal() as db:
        return TelegramNotifier().poll_commands(db)
