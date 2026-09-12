import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def uid() -> str:
    return str(uuid.uuid4())


def now() -> datetime:
    return datetime.now(timezone.utc)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=now, onupdate=now, nullable=False
    )


class Thread(Base, TimestampMixin):
    __tablename__ = "threads"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(200), default="Новый запрос")
    messages: Mapped[list["Message"]] = relationship(back_populates="thread", cascade="all, delete-orphan")


class Message(Base, TimestampMixin):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    thread_id: Mapped[str] = mapped_column(ForeignKey("threads.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    citations: Mapped[list] = mapped_column(JSON, default=list)
    thread: Mapped[Thread] = relationship(back_populates="messages")


class AnalysisRun(Base, TimestampMixin):
    __tablename__ = "analysis_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    thread_id: Mapped[str | None] = mapped_column(ForeignKey("threads.id", ondelete="SET NULL"), index=True)
    message_id: Mapped[str | None] = mapped_column(ForeignKey("messages.id", ondelete="SET NULL"))
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    task_type: Mapped[str] = mapped_column(String(50), default="chat")
    answer: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)


class RunEvent(Base):
    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(40))
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ModelRun(Base):
    __tablename__ = "model_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    analysis_run_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"))
    model: Mapped[str] = mapped_column(String(150))
    purpose: Mapped[str] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(30))
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class ToolRun(Base):
    __tablename__ = "tool_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    analysis_run_id: Mapped[str] = mapped_column(
        ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30))
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    result_summary: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Bank(Base, TimestampMixin):
    __tablename__ = "banks"
    cbr_reg_number: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(300), index=True)
    short_name: Mapped[str | None] = mapped_column(String(200))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    official_url: Mapped[str | None] = mapped_column(String(1000))
    cbr_internal_code: Mapped[str | None] = mapped_column(String(30))
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class WatchlistItem(Base, TimestampMixin):
    __tablename__ = "watchlist"
    cbr_reg_number: Mapped[str] = mapped_column(ForeignKey("banks.cbr_reg_number"), primary_key=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    muted: Mapped[bool] = mapped_column(Boolean, default=False)
    bank: Mapped[Bank] = relationship()


class IntegrationState(Base, TimestampMixin):
    __tablename__ = "integration_state"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)


class SourceDocument(Base, TimestampMixin):
    __tablename__ = "source_documents"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    bank_reg_number: Mapped[str | None] = mapped_column(
        ForeignKey("banks.cbr_reg_number", ondelete="SET NULL"), index=True
    )
    title: Mapped[str] = mapped_column(String(600))
    document_type: Mapped[str] = mapped_column(String(50), default="other")
    reporting_standard: Mapped[str | None] = mapped_column(String(30))
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    source_url: Mapped[str | None] = mapped_column(String(2000))
    source_tier: Mapped[str] = mapped_column(String(30), default="user")
    status: Mapped[str] = mapped_column(String(30), default="uploaded")
    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(Base, TimestampMixin):
    __tablename__ = "document_versions"
    __table_args__ = (UniqueConstraint("document_id", "sha256", name="uq_document_sha"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("source_documents.id", ondelete="CASCADE"), index=True
    )
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    mime_type: Mapped[str] = mapped_column(String(120))
    size_bytes: Mapped[int] = mapped_column(Integer)
    storage_path: Mapped[str] = mapped_column(String(1000))
    extracted_text: Mapped[str | None] = mapped_column(Text)
    parsed_data: Mapped[dict] = mapped_column(JSON, default=dict)
    document: Mapped[SourceDocument] = relationship(back_populates="versions")


class ProvenanceRef(Base):
    __tablename__ = "provenance_refs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    source_url: Mapped[str | None] = mapped_column(String(2000))
    page: Mapped[int | None] = mapped_column(Integer)
    sheet: Mapped[str | None] = mapped_column(String(200))
    cell_range: Mapped[str | None] = mapped_column(String(100))
    table_name: Mapped[str | None] = mapped_column(String(300))
    excerpt: Mapped[str | None] = mapped_column(Text)


class FinancialFact(Base, TimestampMixin):
    __tablename__ = "financial_facts"
    __table_args__ = (Index("ix_fact_metric_period", "metric_code", "period_end"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id", ondelete="CASCADE"), index=True
    )
    provenance_id: Mapped[str] = mapped_column(ForeignKey("provenance_refs.id", ondelete="CASCADE"))
    bank_reg_number: Mapped[str | None] = mapped_column(
        ForeignKey("banks.cbr_reg_number", ondelete="SET NULL")
    )
    metric_code: Mapped[str] = mapped_column(String(100), index=True)
    label: Mapped[str] = mapped_column(String(400))
    value: Mapped[Decimal] = mapped_column(Numeric(38, 8))
    currency: Mapped[str | None] = mapped_column(String(10))
    unit_scale: Mapped[int] = mapped_column(Integer, default=1)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    scope: Mapped[str] = mapped_column(String(30), default="group")
    confidence: Mapped[str] = mapped_column(String(20), default="medium")


class CalendarEvent(Base, TimestampMixin):
    __tablename__ = "calendar_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    external_key: Mapped[str | None] = mapped_column(String(500), unique=True)
    title: Mapped[str] = mapped_column(String(600))
    event_type: Mapped[str] = mapped_column(String(80))
    bank_reg_number: Mapped[str | None] = mapped_column(
        ForeignKey("banks.cbr_reg_number", ondelete="SET NULL"), index=True
    )
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(30), default="confirmed")
    confidence: Mapped[str] = mapped_column(String(20), default="high")
    source_url: Mapped[str | None] = mapped_column(String(2000))
    period_end: Mapped[date | None] = mapped_column(Date)
    notified_24h: Mapped[bool] = mapped_column(Boolean, default=False)
    notified_published: Mapped[bool] = mapped_column(Boolean, default=False)
    bank: Mapped[Bank | None] = relationship()


class Report(Base, TimestampMixin):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    title: Mapped[str] = mapped_column(String(500))
    report_kind: Mapped[str] = mapped_column(String(30), default="financial")
    status: Mapped[str] = mapped_column(String(30), default="queued")
    analysis_run_id: Mapped[str | None] = mapped_column(ForeignKey("analysis_runs.id", ondelete="SET NULL"))
    document_ids: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str | None] = mapped_column(Text)
    idempotency_key: Mapped[str | None] = mapped_column(String(100), unique=True)
    artifacts: Mapped[list["Artifact"]] = relationship(back_populates="report", cascade="all, delete-orphan")


class Artifact(Base, TimestampMixin):
    __tablename__ = "artifacts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=uid)
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    format: Mapped[str] = mapped_column(String(20))
    mime_type: Mapped[str] = mapped_column(String(120))
    storage_path: Mapped[str] = mapped_column(String(1000))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64))
    report: Mapped[Report] = relationship(back_populates="artifacts")
