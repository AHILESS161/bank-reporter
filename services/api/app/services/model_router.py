import json
import time
from typing import Any

from openai import OpenAI
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ModelRun


class ModelUnavailable(RuntimeError):
    pass


class ModelRouter:
    def __init__(self, db: Session, analysis_run_id: str | None = None):
        self.db = db
        self.analysis_run_id = analysis_run_id
        self.settings = get_settings()
        self.client = OpenAI(
            api_key=self.settings.openrouter_api_key or "missing", base_url=self.settings.openrouter_base_url
        )

    @property
    def configured(self) -> bool:
        key = self.settings.openrouter_api_key.strip()
        if not key:
            return False
        if "openrouter.ai" in self.settings.openrouter_base_url:
            return key.startswith("sk-or-v1-")
        return True

    @property
    def configuration_error(self) -> str:
        key = self.settings.openrouter_api_key.strip()
        if not key:
            return "OPENROUTER_API_KEY не задан в корневом .env"
        if "openrouter.ai" in self.settings.openrouter_base_url and not key.startswith("sk-or-v1-"):
            return "В OPENROUTER_API_KEY указан ключ другого провайдера. Нужен ключ OpenRouter формата sk-or-v1-…"
        return ""

    def chat(self, messages: list[dict], tools: list[dict] | None = None, model: str | None = None):
        if not self.configured:
            raise ModelUnavailable(self.configuration_error)
        selected = model or self.settings.orchestrator_model
        started = time.monotonic()
        record = ModelRun(
            analysis_run_id=self.analysis_run_id, model=selected, purpose="orchestration", status="running"
        )
        self.db.add(record)
        self.db.commit()
        try:
            response = self.client.chat.completions.create(
                model=selected,
                messages=messages,
                tools=tools or None,
                tool_choice="auto" if tools else None,
                temperature=0.1,
                timeout=120,
                extra_headers={"HTTP-Referer": self.settings.web_origin, "X-Title": "Bank Reporter"},
            )
            record.status = "completed"
            record.latency_ms = int((time.monotonic() - started) * 1000)
            if response.usage:
                record.input_tokens = response.usage.prompt_tokens
                record.output_tokens = response.usage.completion_tokens
            self.db.commit()
            return response.choices[0].message
        except Exception as exc:
            record.status = "failed"
            record.error = str(exc)[:2000]
            record.latency_ms = int((time.monotonic() - started) * 1000)
            self.db.commit()
            raise

    def finance_narrative(self, facts: list[dict], question: str) -> dict[str, Any]:
        if not facts:
            return {
                "summary": "В документах не найдено достаточно нормализованных финансовых показателей.",
                "highlights": [],
                "risks": ["Проверьте качество извлечения таблиц и отчетный период."],
                "chart": {"template": "F1", "metric_codes": []},
            }
        if not self.configured:
            return self._deterministic_narrative(facts)
        prompt = (
            "Ты финансовый аналитик банковской отчетности. Используй только переданные факты. "
            "Не пересчитывай значения мысленно и не добавляй числа. Верни JSON с ключами summary, highlights, risks, chart. "
            "Каждый highlights элемент: {text, fact_ids:[...]}; fact_ids обязаны существовать. "
            "chart: {template, metric_codes}; template только F1,F2,F3,F6,F7,F8,F9,F10,F11,F12,F13,F17,L16. "
            f"Вопрос: {question}\nФакты: {json.dumps(facts, ensure_ascii=False, default=str)}"
        )
        last_error: Exception | None = None
        for model in (self.settings.finance_model, self.settings.finance_fallback_model):
            attempts = 2 if model == self.settings.finance_model else 1
            for _ in range(attempts):
                try:
                    message = self.chat(
                        [
                            {"role": "system", "content": "Ответ только валидным JSON без markdown."},
                            {"role": "user", "content": prompt},
                        ],
                        model=model,
                    )
                    data = json.loads(message.content or "{}")
                    self._validate_narrative(data, {item["id"] for item in facts})
                    return data
                except Exception as exc:
                    last_error = exc
        raise ModelUnavailable(f"Финансовые модели не прошли проверку: {last_error}")

    @staticmethod
    def _validate_narrative(data: dict, fact_ids: set[str]) -> None:
        if not isinstance(data.get("summary"), str) or not isinstance(data.get("highlights"), list):
            raise ValueError("Неверная схема финансового ответа")
        allowed = {"F1", "F2", "F3", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "F13", "F17", "L16"}
        if data.get("chart", {}).get("template") not in allowed:
            raise ValueError("Неподдерживаемый шаблон")
        for item in data["highlights"]:
            refs = item.get("fact_ids", [])
            if not refs or not set(refs).issubset(fact_ids):
                raise ValueError("Вывод без проверяемых fact_ids")

    @staticmethod
    def _deterministic_narrative(facts: list[dict]) -> dict:
        first = facts[:5]
        return {
            "summary": "Показатели извлечены и подготовлены к проверяемому анализу. Для модельной интерпретации задайте OPENROUTER_API_KEY.",
            "highlights": [
                {"text": f"{item['label']}: {item['value']}", "fact_ids": [item["id"]]} for item in first
            ],
            "risks": ["Автоматическое извлечение необходимо сверить с первоисточником."],
            "chart": {"template": "F1", "metric_codes": [item["metric_code"] for item in first]},
        }
