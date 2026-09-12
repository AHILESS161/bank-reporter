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

    @staticmethod
    def _result(response: httpx.Response) -> dict:
        try:
            payload = response.json()
        except ValueError:
            response.raise_for_status()
            raise ValueError("Telegram вернул непонятный ответ")
        if not response.is_success or not payload.get("ok"):
            raise ValueError(f"Telegram: {payload.get('description', 'ошибка подключения')}")
        return payload

    def send(self, text: str, chat_id: str | None = None) -> bool:
        target = chat_id or self.settings.telegram_chat_id
        if not self.settings.telegram_bot_token or not target:
            return False
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/sendMessage"
        response = httpx.post(
            url,
            json={
                "chat_id": target,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=20,
        )
        self._result(response)
        return True

    def bot_info(self) -> dict:
        if not self.settings.telegram_bot_token:
            raise ValueError("Сначала сохраните токен Telegram-бота")
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/getMe"
        response = httpx.get(url, timeout=15)
        payload = self._result(response)
        return payload.get("result", {})

    def discover_chat(self) -> dict:
        """Return the most recent direct chat that contacted this bot."""
        self.bot_info()
        url = f"https://api.telegram.org/bot{self.settings.telegram_bot_token}/getUpdates"
        response = httpx.get(url, params={"timeout": 0, "limit": 100}, timeout=15)
        updates = self._result(response).get("result", [])
        for update in reversed(updates):
            message = update.get("message") or update.get("channel_post") or {}
            chat = message.get("chat") or {}
            if chat.get("id") is None:
                continue
            title = chat.get("title") or " ".join(
                part for part in (chat.get("first_name"), chat.get("last_name")) if part
            )
            return {
                "chat_id": str(chat["id"]),
                "title": title or chat.get("username") or "Telegram chat",
                "type": chat.get("type", "unknown"),
            }
        raise ValueError("Сообщений не найдено. Откройте бота в Telegram, нажмите Start и повторите поиск")

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
        state.value = {**(state.value or {}), "update_offset": offset}
        db.commit()
        return handled
