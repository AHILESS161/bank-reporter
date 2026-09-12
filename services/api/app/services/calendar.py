from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from icalendar import Calendar, Event
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Bank, CalendarEvent, SourceDocument, WatchlistItem
from .cbr import CBR_KEY_RATE_DECISION, CBRConnector, discover_document_links
from .documents import DocumentService
from .financial import forecast_lag_days
from .minfin import MinfinConnector
from .network import public_get
from .telegram import TelegramNotifier


class CalendarService:
    def __init__(self, db: Session):
        self.db = db

    def sync_cbr(self) -> int:
        count = 0
        source_events = CBRConnector().sync_editorial_calendar() + MinfinConnector().discover_publications()
        for item in source_events:
            existing = self.db.scalar(
                select(CalendarEvent).where(CalendarEvent.external_key == item["external_key"])
            )
            if existing:
                changed = existing.starts_at != item["starts_at"]
                was_published = existing.status == "published"
                published_url = existing.source_url
                for key, value in item.items():
                    setattr(existing, key, value)
                if was_published and item["status"] != "published":
                    existing.status = "published"
                    existing.source_url = published_url
                elif changed and item["status"] != "published":
                    existing.status = "changed"
            else:
                self.db.add(CalendarEvent(**item))
                count += 1
        self.db.commit()
        return count

    def forecast_watchlist(self) -> int:
        created = 0
        watches = self.db.scalars(select(WatchlistItem).where(WatchlistItem.enabled.is_(True))).all()
        for watch in watches:
            history = self.db.scalars(
                select(CalendarEvent)
                .where(
                    CalendarEvent.bank_reg_number == watch.cbr_reg_number, CalendarEvent.status == "published"
                )
                .order_by(CalendarEvent.period_end)
            ).all()
            grouped: dict[str, list[CalendarEvent]] = {}
            for item in history:
                grouped.setdefault(item.event_type, []).append(item)
            for event_type, events in grouped.items():
                dated = [item for item in events if item.period_end]
                lags = [(item.starts_at.date() - item.period_end).days for item in dated]
                lag = forecast_lag_days(lags)
                if lag is None or not dated:
                    continue
                last = dated[-1]
                next_period = last.period_end + (
                    timedelta(days=365) if event_type.endswith("annual") else timedelta(days=91)
                )
                predicted = datetime.combine(
                    next_period + timedelta(days=lag),
                    datetime.min.time().replace(hour=10),
                    ZoneInfo("Europe/Moscow"),
                )
                key = f"forecast:{watch.cbr_reg_number}:{event_type}:{next_period}"
                if not self.db.scalar(select(CalendarEvent).where(CalendarEvent.external_key == key)):
                    self.db.add(
                        CalendarEvent(
                            external_key=key,
                            title=f"Ожидаемая публикация: {watch.bank.name}",
                            event_type=event_type,
                            bank_reg_number=watch.cbr_reg_number,
                            starts_at=predicted,
                            period_end=next_period,
                            status="forecast",
                            confidence="low",
                        )
                    )
                    created += 1
        self.db.commit()
        return created

    def sync_key_rate_publication(self) -> int:
        published_on = CBRConnector().latest_key_rate_decision()
        if not published_on:
            return 0
        event = self.db.scalar(
            select(CalendarEvent).where(
                CalendarEvent.external_key == f"cbr:key_rate_meeting:{published_on}"
            )
        )
        if not event or event.status == "published":
            return 0
        event.status = "published"
        event.source_url = CBR_KEY_RATE_DECISION
        self.db.commit()
        return 1

    def monitor_expected_publications(self, now: datetime | None = None) -> int:
        """Check explicit watchlist sources only during the expected Moscow publication window."""

        moscow = ZoneInfo("Europe/Moscow")
        current = (now or datetime.now(timezone.utc)).astimezone(moscow)
        if current.hour < 8 or current.hour >= 20:
            return 0
        day_start = datetime.combine(current.date(), datetime.min.time(), moscow).astimezone(timezone.utc)
        day_end = day_start + timedelta(days=1)
        events = self.db.scalars(
            select(CalendarEvent).where(
                CalendarEvent.bank_reg_number.is_not(None),
                CalendarEvent.starts_at >= day_start,
                CalendarEvent.starts_at < day_end,
                CalendarEvent.status.in_(("confirmed", "forecast", "changed")),
            )
        ).all()
        published = 0
        notifier = TelegramNotifier()
        for event in events:
            watch = self.db.get(WatchlistItem, event.bank_reg_number)
            bank = self.db.get(Bank, event.bank_reg_number)
            if not watch or not watch.enabled or not bank or not bank.official_url:
                continue
            try:
                final_url, content = public_get(bank.official_url, timeout=30)
                period = str(event.period_end.year) if event.period_end else None
                links = discover_document_links(
                    final_url, content.decode("utf-8", errors="replace"), period=period
                )
            except Exception:
                continue
            for link in links:
                if self.db.scalar(select(SourceDocument).where(SourceDocument.source_url == link["url"])):
                    continue
                try:
                    document = DocumentService(self.db).download(
                        link["url"],
                        title=link["title"],
                        source_tier="official_bank",
                        bank_reg_number=event.bank_reg_number,
                        document_type=event.event_type,
                        reporting_standard=link.get("reporting_standard"),
                    )
                except Exception:
                    continue
                event.status = "published"
                event.source_url = document.source_url
                event.notified_published = not watch.muted and notifier.send(
                    f"Опубликован ожидаемый документ: {event.title}\n{document.source_url or ''}"
                )
                published += 1
                break
        self.db.commit()
        return published

    def to_ics(self, events: list[CalendarEvent]) -> bytes:
        calendar = Calendar()
        calendar.add("prodid", "-//Bank Reporter//RU")
        calendar.add("version", "2.0")
        for item in events:
            event = Event()
            event.add("uid", f"{item.id}@bank-reporter.local")
            event.add("summary", item.title)
            event.add("dtstart", item.starts_at)
            if item.ends_at:
                event.add("dtend", item.ends_at)
            event.add("description", f"Статус: {item.status}; уверенность: {item.confidence}")
            if item.source_url:
                event.add("url", item.source_url)
            calendar.add_component(event)
        return calendar.to_ical()


def upcoming(db: Session, days: int = 7) -> list[CalendarEvent]:
    start = datetime.now(timezone.utc)
    end = start + timedelta(days=days)
    return list(
        db.scalars(
            select(CalendarEvent)
            .where(CalendarEvent.starts_at >= start, CalendarEvent.starts_at <= end)
            .order_by(CalendarEvent.starts_at)
        ).all()
    )
