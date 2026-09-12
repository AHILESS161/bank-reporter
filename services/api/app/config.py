from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    app_name: str = "Bank Reporter"
    environment: str = "development"
    app_timezone: str = "Europe/Moscow"
    web_origin: str = "http://localhost:3000"
    database_url: str = "sqlite:///./bank_reporter.sqlite3"
    redis_url: str = "redis://localhost:6379/0"
    browser_service_url: str = "http://localhost:8787"
    data_dir: Path = Path("./data")
    lieflat_dir: Path = Path("/opt/lieflat-charts")

    model_api_key: str = ""
    model_base_url: str = ""
    openrouter_api_key: str = ""
    openrouter_base_url: str = "https://openrouter.ai/api/v1"
    orchestrator_model: str = "deepseek/deepseek-v4.1-flash"
    finance_model: str = "inclusionai/ling-3.0-flash-fin"
    finance_fallback_model: str = "deepseek/deepseek-v4.1-flash"

    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    max_agent_steps: int = Field(12, ge=1, le=30)
    max_web_pages: int = Field(25, ge=1, le=100)
    max_file_mb: int = Field(100, ge=1, le=500)
    max_archive_mb: int = Field(500, ge=1, le=2000)
    trusted_media_domains: str = (
        "interfax.ru,rbc.ru,kommersant.ru,vedomosti.ru,tass.ru,frankmedia.ru,banki.ru"
    )

    @property
    def trusted_domains(self) -> set[str]:
        return {item.strip().lower() for item in self.trusted_media_domains.split(",") if item.strip()}

    @property
    def effective_model_api_key(self) -> str:
        return (self.model_api_key or self.openrouter_api_key).strip()

    @property
    def effective_model_base_url(self) -> str:
        return (self.model_base_url or self.openrouter_base_url).rstrip("/")

    @property
    def model_provider(self) -> str:
        base_url = self.effective_model_base_url.lower()
        if "routerai.ru" in base_url:
            return "RouterAI"
        if "openrouter.ai" in base_url:
            return "OpenRouter"
        if "api.deepseek.com" in base_url:
            return "DeepSeek API"
        return "OpenAI-compatible API"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    for part in ("documents", "artifacts", "tmp"):
        (settings.data_dir / part).mkdir(parents=True, exist_ok=True)
    return settings
