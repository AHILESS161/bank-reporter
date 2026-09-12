from datetime import datetime
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.models import Bank, CalendarEvent, WatchlistItem
from app.services.calendar import CalendarService
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
