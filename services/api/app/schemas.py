from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ThreadCreate(BaseModel):
    title: str = Field("Новый запрос", max_length=200)


class ThreadOut(ORMModel):
    id: str
    title: str
    created_at: datetime


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=20_000)


class MessageOut(ORMModel):
    id: str
    role: str
    content: str
    citations: list[Any] = []
    created_at: datetime


class RunCreated(BaseModel):
    run_id: str


class BankOut(ORMModel):
    cbr_reg_number: str
    name: str
    short_name: str | None = None
    aliases: list[str] = []
    official_url: str | None = None


class WatchlistPut(BaseModel):
    bank_name: str | None = None


class WatchlistOut(BaseModel):
    cbr_reg_number: str
    bank_name: str
    enabled: bool
    muted: bool = False


class DocumentDiscover(BaseModel):
    bank_query: str
    document_type: str | None = None
    period: str | None = None
    idempotency_key: str | None = None


class DocumentOut(ORMModel):
    id: str
    title: str
    document_type: str
    reporting_standard: str | None = None
    source_url: str | None = None
    source_tier: str
    status: str
    created_at: datetime


class ArticleSearch(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    bank: str | None = None
    date_from: date | None = None
    date_to: date | None = None
    domains: list[str] = []
    limit: int = Field(20, ge=1, le=50)


class ArticleOut(BaseModel):
    title: str
    url: str
    source: str
    published_at: datetime | None = None
    author: str | None = None
    language: str | None = None
    excerpt: str = ""
    trust_tier: str = "other"
    score: float = 0


class CalendarOut(ORMModel):
    id: str
    title: str
    event_type: str
    starts_at: datetime
    ends_at: datetime | None = None
    status: str
    confidence: str
    source_url: str | None = None
    bank_name: str | None = None


class ReportCreate(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    document_ids: list[str] = Field(min_length=1)
    report_kind: str = Field("financial", pattern="^(financial|comparison|brief)$")
    question: str = Field("Проанализируй ключевые изменения", max_length=5000)
    output_formats: list[str] = ["html", "pdf", "png", "xlsx", "csv"]
    idempotency_key: str | None = None


class ArtifactOut(ORMModel):
    id: str
    format: str
    mime_type: str
    size_bytes: int


class ReportOut(ORMModel):
    id: str
    title: str
    report_kind: str
    status: str
    summary: str | None = None
    created_at: datetime
    artifacts: list[ArtifactOut] = []


class FinancialFactOut(ORMModel):
    metric_code: str
    label: str
    value: Decimal
    currency: str | None
    unit_scale: int
    period_end: date | None
    confidence: str
