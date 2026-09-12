from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import CalendarEvent, IntegrationState, WatchlistItem


class TelegramNotifier:
    def __init__(self):
        self.settings = get_settings()

    @property
    def configured(self) -> bool:
        return bool(self.settings.telegram_bot_token and self.settings.telegram_chat_id)

    def send(self, text: str, chat_id: str | None = None) -> bool:
        if not self.configured:
            return False
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        response = httpx.post(
            url,
            json={
                "chat_id": chat_id or self.settings.telegram_chat_id,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        response.raise_for_status()
        return True

    def digest(self, events: list[CalendarEvent]) -> bool:
        if not events:
            return False
        lines = ["Bank Reporter — ближайшие события"]
        for item in events[:20]:
            local = item.starts_at.astimezone(ZoneInfo("Europe/Moscow"))
            marker = "~" if item.status == "forecast" else "•"
            lines.append(f"{marker} {local:%d.%m %H:%M} — {item.title}")
        return self.send("\n".join(lines))

    def handle_command(self, db: Session, command: str) -> str:
        name = command.strip().split()[0].split("@")[0].casefold()
        if name in {"/mute", "/unmute"}:
            muted = name == "/mute"
            items = db.scalars(select(WatchlistItem)).all()
            for item in items:
                item.muted = muted
            db.commit()
            return "Уведомления отключены." if muted else "Уведомления включены."
        if name in {"/today", "/week"}:
            moscow = ZoneInfo("Europe/Moscow")
            now = datetime.now(moscow)
            start = datetime.combine(now.date(), time.min, moscow).astimezone(timezone.utc)
            end = (
                start + timedelta(days=1)
                if name == "/today"
                else datetime.now(timezone.utc) + timedelta(days=7)
            )
            events = db.scalars(
                select(CalendarEvent)
                .where(CalendarEvent.starts_at >= start, CalendarEvent.starts_at < end)
                .order_by(CalendarEvent.starts_at)
            ).all()
            if not events:
                return "Событий на сегодня нет." if name == "/today" else "Событий на неделю нет."
            lines = ["Сегодня:" if name == "/today" else "Ближайшие 7 дней:"]
            for item in events[:20]:
                marker = "~" if item.status == "forecast" else "•"
                lines.append(f"{marker} {item.starts_at.astimezone(moscow):%d.%m %H:%M} — {item.title}")
            return "\n".join(lines)
        return "Команды: /today, /week, /mute, /unmute"

    def poll_commands(self, db: Session) -> int:
        if not self.configured:
            return 0
        state = db.get(IntegrationState, "telegram")
        offset = int((state.value if state else {}).get("update_offset", 0))
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/getUpdates"
        response = httpx.get(url, params={"offset": offset, "timeout": 0}, timeout=10)
        response.raise_for_status()
        updates = response.json().get("result", [])
        handled = 0
        allowed_chat = str(self.settings.telegram_chat_id)
        for update in updates:
            offset = max(offset, int(update.get("update_id", 0)) + 1)
            message = update.get("message") or {}
            chat_id = str((message.get("chat") or {}).get("id", ""))
            command = str(message.get("text", ""))
            if chat_id != allowed_chat or not command.startswith("/"):
                continue
            self.send(self.handle_command(db, command), chat_id)
            handled += 1
        if state is None:
            state = IntegrationState(key="telegram", value={})
            db.add(state)
        state.value = {**state.value, "update_offset": offset}
        db.commit()
        return handled
