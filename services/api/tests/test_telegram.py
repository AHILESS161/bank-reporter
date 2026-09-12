from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Bank, CalendarEvent, WatchlistItem
from app.services.calendar import CalendarService
from app.services.cbr import CBRConnector
from app.services.telegram import TelegramNotifier


def test_telegram_mute_commands_update_watchlist():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add(Bank(cbr_reg_number="1", name="Тест Банк"))
        db.add(WatchlistItem(cbr_reg_number="1"))
        db.commit()
        notifier = TelegramNotifier()
        assert notifier.handle_command(db, "/mute") == "Уведомления отключены."
        assert db.get(WatchlistItem, "1").muted is True
        assert notifier.handle_command(db, "/unmute") == "Уведомления включены."
        assert db.get(WatchlistItem, "1").muted is False


def test_today_command_marks_forecasts():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    now = datetime.now(ZoneInfo("Europe/Moscow"))
    with Session(engine) as db:
        db.add(
            CalendarEvent(
                title="Ожидаемая отчетность",
                event_type="ifrs",
                starts_at=now.replace(hour=10, minute=0),
                status="forecast",
            )
        )
        db.commit()
        response = TelegramNotifier().handle_command(db, "/today")
        assert "~" in response
        assert "Ожидаемая отчетность" in response


def test_expected_monitor_stays_idle_outside_window():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        value = CalendarService(db).monitor_expected_publications(
            datetime(2026, 1, 1, 3, 0, tzinfo=ZoneInfo("Europe/Moscow"))
        )
        assert value == 0


def test_key_rate_event_becomes_clickable_only_after_publication(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        event = CalendarEvent(
            external_key="cbr:key_rate_meeting:2026-09-11",
            title="Решение по ключевой ставке",
            event_type="key_rate_meeting",
            starts_at=datetime(2026, 9, 11, 13, 30, tzinfo=ZoneInfo("Europe/Moscow")),
            status="confirmed",
            source_url="https://www.cbr.ru/dkp/cal_mp/",
        )
        db.add(event)
        db.commit()
        monkeypatch.setattr(CBRConnector, "latest_key_rate_decision", lambda *_: date(2026, 9, 11))

        assert CalendarService(db).sync_key_rate_publication() == 1
        db.refresh(event)
        assert event.status == "published"
        assert event.source_url == "https://www.cbr.ru/press/keypr/"
