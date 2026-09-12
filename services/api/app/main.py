import asyncio
import json
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings, update_runtime_settings
from .db import SessionLocal, create_schema, get_db
from .local_runtime import dispatch_task, start_local_scheduler, stop_local_scheduler
from .skills import build_skill_registry, build_workflow_registry
from .skills.contracts import WorkflowManifest
from .skills.workflows import WorkflowValidationError
from .models import (
    AnalysisRun,
    Artifact,
    Bank,
    CalendarEvent,
    IntegrationState,
    Message,
    Report,
    RunEvent,
    SourceDocument,
    Thread,
    WatchlistItem,
)
from .schemas import (
    ArticleOut,
    ArticleSearch,
    BankOut,
    CalendarOut,
    DocumentDiscover,
    DocumentOut,
    MessageCreate,
    MessageOut,
    ReportCreate,
    ReportOut,
    RuntimeSettingsUpdate,
    RunCreated,
    ThreadCreate,
    ThreadOut,
    WatchlistOut,
    WatchlistPut,
)
from .services.browser import BrowserClient
from .services.calendar import CalendarService
from .services.cbr import CBRConnector
from .services.documents import DocumentService
from .services.storage import Storage
from .services.model_router import ModelRouter, ModelUnavailable
from .services.telegram import TelegramNotifier
from .tasks import create_report as create_report_task
from .tasks import run_agent, sync_calendar


settings = get_settings()
skill_registry = build_skill_registry()
workflow_registry = build_workflow_registry(skill_registry)


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_schema()
    if settings.environment != "test":
        try:
            dispatch_task(sync_calendar)
        except Exception:
            pass
    start_local_scheduler()
    try:
        yield
    finally:
        stop_local_scheduler()


app = FastAPI(
    title="Bank Reporter API",
    version="0.2.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.web_origin],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    key = settings.effective_model_api_key
    configured = bool(key) and (
        "openrouter.ai" not in settings.effective_model_base_url or key.startswith("sk-or-v1-")
    )
    openrouter_configured = bool(settings.openrouter_api_key) and settings.openrouter_api_key.startswith(
        "sk-or-v1-"
    )
    return {
        "status": "ok",
        "model_configured": configured,
        "openrouter_configured": openrouter_configured,
        "skills": len(skill_registry.manifests()),
        "workflows": len(workflow_registry.catalog()),
    }


@app.get("/api/skills")
def list_skills():
    """Return the safe, non-secret capability catalog used by the agent."""
    return skill_registry.catalog()


@app.get("/api/workflows")
def list_workflows(db: Session = Depends(get_db)):
    """Return validated workflow graphs for the constructor UI."""
    state = db.get(IntegrationState, "custom_workflows")
    custom = state.value.get("items", []) if state else []
    try:
        return build_workflow_registry(skill_registry, custom).catalog()
    except (ValueError, WorkflowValidationError):
        return workflow_registry.catalog()


@app.post("/api/workflows/validate")
def validate_workflow(payload: WorkflowManifest):
    """Validate a proposed graph without executing any skill."""
    try:
        workflow_registry.validate(payload)
        ordered = workflow_registry._topological_nodes(payload)
    except WorkflowValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"valid": True, "order": [node.id for node in ordered]}


@app.put("/api/workflows/{workflow_id}")
def save_workflow(
    workflow_id: str, payload: WorkflowManifest, db: Session = Depends(get_db)
):
    if workflow_id != payload.id:
        raise HTTPException(400, "Workflow id in path and body must match")
    if workflow_id in {item["id"] for item in workflow_registry.catalog()}:
        raise HTTPException(409, "Встроенный workflow нельзя перезаписать")
    editable = payload.model_copy(update={"editable": True})
    try:
        workflow_registry.validate(editable)
    except WorkflowValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    state = db.get(IntegrationState, "custom_workflows")
    items = list(state.value.get("items", [])) if state else []
    encoded = editable.model_dump(mode="json")
    items = [item for item in items if item.get("id") != workflow_id] + [encoded]
    if state:
        state.value = {"items": items}
    else:
        db.add(IntegrationState(key="custom_workflows", value={"items": items}))
    db.commit()
    return encoded


@app.delete("/api/workflows/{workflow_id}")
def delete_workflow(workflow_id: str, db: Session = Depends(get_db)):
    if workflow_id in {item["id"] for item in workflow_registry.catalog()}:
        raise HTTPException(409, "Встроенный workflow нельзя удалить")
    state = db.get(IntegrationState, "custom_workflows")
    if not state:
        raise HTTPException(404, "Workflow not found")
    items = list(state.value.get("items", []))
    filtered = [item for item in items if item.get("id") != workflow_id]
    if len(filtered) == len(items):
        raise HTTPException(404, "Workflow not found")
    state.value = {"items": filtered}
    db.commit()
    return Response(status_code=204)


@app.get("/api/settings/status")
def settings_status():
    """Return only non-secret runtime configuration for the local UI."""
    key = settings.effective_model_api_key
    format_valid = bool(key) and (
        "openrouter.ai" not in settings.effective_model_base_url or key.startswith("sk-or-v1-")
    )
    openrouter_configured = bool(settings.openrouter_api_key) and settings.openrouter_api_key.startswith(
        "sk-or-v1-"
    )
    return {
        "model_configured": format_valid,
        "model_key_present": bool(key),
        "model_provider": settings.model_provider,
        "model_error": (
            ""
            if format_valid
            else (
                "Для OpenRouter нужен ключ формата sk-or-v1-…"
                if key and settings.model_provider == "OpenRouter"
                else "Ключ модели не найден в корневом .env"
            )
        ),
        "openrouter_configured": openrouter_configured,
        "openrouter_key_present": bool(settings.openrouter_api_key),
        "openrouter_error": (
            ""
            if format_valid
            else (
                "Нужен ключ OpenRouter формата sk-or-v1-…"
                if key
                else "Ключ не найден в корневом .env"
            )
        ),
        "orchestrator_model": settings.orchestrator_model,
        "finance_model": settings.finance_model,
        "model_base_url": settings.effective_model_base_url,
        "telegram_configured": bool(settings.telegram_bot_token and settings.telegram_chat_id),
        "telegram_token_present": bool(settings.telegram_bot_token),
        "telegram_chat_id": settings.telegram_chat_id,
        "trusted_media_domains": settings.trusted_media_domains,
        "max_agent_steps": settings.max_agent_steps,
        "max_web_pages": settings.max_web_pages,
        "max_file_mb": settings.max_file_mb,
        "max_archive_mb": settings.max_archive_mb,
    }


@app.put("/api/settings")
def save_settings(payload: RuntimeSettingsUpdate):
    values = payload.model_dump(exclude_none=True)
    clear_model = values.pop("clear_model_api_key", False)
    clear_telegram = values.pop("clear_telegram_bot_token", False)
    if clear_model:
        values["model_api_key"] = ""
    elif not values.get("model_api_key"):
        values.pop("model_api_key", None)
    if clear_telegram:
        values["telegram_bot_token"] = ""
    elif not values.get("telegram_bot_token"):
        values.pop("telegram_bot_token", None)
    if "model_base_url" in values:
        base_url = str(values["model_base_url"]).strip().rstrip("/")
        if not base_url.startswith(("https://", "http://")):
            raise HTTPException(422, "Адрес API должен начинаться с https:// или http://")
        values["model_base_url"] = base_url
    if "telegram_chat_id" in values:
        values["telegram_chat_id"] = str(values["telegram_chat_id"]).strip()
    update_runtime_settings(values)
    return settings_status()


@app.post("/api/settings/model/test")
def test_model_connection(db: Session = Depends(get_db)):
    router = ModelRouter(db)
    if not router.configured:
        raise HTTPException(422, router.configuration_error)
    try:
        message = router.chat(
            [
                {"role": "system", "content": "Ответь одним словом: OK"},
                {"role": "user", "content": "Проверка подключения"},
            ]
        )
    except ModelUnavailable as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Провайдер модели недоступен: {str(exc)[:500]}") from exc
    return {"ok": True, "provider": settings.model_provider, "answer": message.content or "OK"}


@app.post("/api/settings/telegram/discover")
def discover_telegram_chat():
    try:
        return TelegramNotifier().discover_chat()
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/settings/telegram/test")
def test_telegram():
    notifier = TelegramNotifier()
    if not notifier.configured:
        raise HTTPException(422, "Сохраните токен бота и Chat ID")
    try:
        info = notifier.bot_info()
        notifier.send("Bank Reporter: тестовое уведомление доставлено ✅")
    except (ValueError, httpx.HTTPError) as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"ok": True, "bot": info.get("username", "Telegram bot")}


@app.post("/api/threads", response_model=ThreadOut)
def create_thread(payload: ThreadCreate, db: Session = Depends(get_db)):
    item = Thread(title=payload.title)
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@app.get("/api/threads", response_model=list[ThreadOut])
def list_threads(db: Session = Depends(get_db)):
    return list(db.scalars(select(Thread).order_by(Thread.updated_at.desc()).limit(100)).all())


@app.delete("/api/threads/{thread_id}")
def delete_thread(thread_id: str, db: Session = Depends(get_db)):
    item = db.get(Thread, thread_id)
    if not item:
        raise HTTPException(404, "Thread not found")
    active_run = db.scalar(
        select(AnalysisRun).where(
            AnalysisRun.thread_id == thread_id,
            AnalysisRun.status.in_({"queued", "running", "processing"}),
        )
    )
    if active_run:
        raise HTTPException(409, "Дождитесь завершения ответа агента")
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@app.get("/api/threads/{thread_id}/messages", response_model=list[MessageOut])
def thread_messages(thread_id: str, db: Session = Depends(get_db)):
    if not db.get(Thread, thread_id):
        raise HTTPException(404, "Thread not found")
    return list(
        db.scalars(select(Message).where(Message.thread_id == thread_id).order_by(Message.created_at)).all()
    )


@app.post("/api/threads/{thread_id}/messages", response_model=RunCreated)
def send_message(
    thread_id: str,
    payload: MessageCreate,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    db: Session = Depends(get_db),
):
    thread = db.get(Thread, thread_id)
    if not thread:
        raise HTTPException(404, "Thread not found")
    if idempotency_key:
        existing = db.scalar(select(AnalysisRun).where(AnalysisRun.idempotency_key == idempotency_key))
        if existing:
            return RunCreated(run_id=existing.id)
    message = Message(thread_id=thread_id, role="user", content=payload.content)
    thread.updated_at = datetime.now(timezone.utc)
    db.add(message)
    db.flush()
    run = AnalysisRun(
        thread_id=thread_id, message_id=message.id, idempotency_key=idempotency_key, status="queued"
    )
    db.add(run)
    db.commit()
    try:
        dispatch_task(run_agent, run.id)
    except Exception as exc:
        run.status = "failed"
        run.error = f"Очередь недоступна: {exc}"
        db.add(RunEvent(run_id=run.id, type="failed", payload={"error": run.error}))
        db.commit()
    return RunCreated(run_id=run.id)


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str):
    async def stream():
        cursor = 0
        idle = 0
        while idle < 900:
            with SessionLocal() as db:
                run = db.get(AnalysisRun, run_id)
                if not run:
                    yield f"data: {json.dumps({'type': 'failed', 'payload': {'error': 'Run not found'}})}\n\n"
                    return
                events = db.scalars(
                    select(RunEvent)
                    .where(RunEvent.run_id == run_id, RunEvent.id > cursor)
                    .order_by(RunEvent.id)
                ).all()
                for event in events:
                    cursor = event.id
                    yield f"data: {json.dumps({'type': event.type, 'payload': event.payload}, ensure_ascii=False, default=str)}\n\n"
                if run.status in {"completed", "partial", "cancelled", "failed"} and not events:
                    return
            idle += 1
            await asyncio.sleep(1)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str, db: Session = Depends(get_db)):
    run = db.get(AnalysisRun, run_id)
    if not run:
        raise HTTPException(404, "Run not found")
    run.cancel_requested = True
    db.commit()
    return {"status": "cancellation_requested"}


@app.get("/api/banks/search", response_model=list[BankOut])
def search_banks(q: str = Query(min_length=2), db: Session = Depends(get_db)):
    found = CBRConnector().search_banks(q)
    output = []
    for raw in found:
        item = db.get(Bank, raw["cbr_reg_number"])
        values = {
            key: value
            for key, value in raw.items()
            if key in {"cbr_reg_number", "name", "short_name", "aliases", "official_url", "cbr_internal_code"}
        }
        if not item:
            item = Bank(**values)
            db.add(item)
        else:
            for key, value in values.items():
                if key != "cbr_reg_number" and value:
                    setattr(item, key, value)
        output.append(item)
    db.commit()
    return output


@app.get("/api/watchlist", response_model=list[WatchlistOut])
def watchlist(db: Session = Depends(get_db)):
    return [
        WatchlistOut(
            cbr_reg_number=item.cbr_reg_number,
            bank_name=item.bank.name,
            enabled=item.enabled,
            muted=item.muted,
        )
        for item in db.scalars(select(WatchlistItem).order_by(WatchlistItem.created_at.desc())).all()
    ]


@app.put("/api/watchlist/{reg_number}", response_model=WatchlistOut)
def watch(reg_number: str, payload: WatchlistPut, db: Session = Depends(get_db)):
    bank = db.get(Bank, reg_number)
    if not bank:
        if not payload.bank_name:
            raise HTTPException(404, "Сначала найдите банк")
        bank = Bank(cbr_reg_number=reg_number, name=payload.bank_name, short_name=payload.bank_name)
        db.add(bank)
        db.flush()
    item = db.get(WatchlistItem, reg_number)
    if not item:
        item = WatchlistItem(cbr_reg_number=reg_number)
        db.add(item)
    else:
        item.enabled = True
    db.commit()
    return WatchlistOut(
        cbr_reg_number=reg_number, bank_name=bank.name, enabled=item.enabled, muted=item.muted
    )


@app.delete("/api/watchlist/{reg_number}")
def unwatch(reg_number: str, db: Session = Depends(get_db)):
    item = db.get(WatchlistItem, reg_number)
    if not item:
        raise HTTPException(404, "Watchlist item not found")
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@app.get("/api/documents", response_model=list[DocumentOut])
def list_documents(db: Session = Depends(get_db)):
    items = db.scalars(
        select(SourceDocument).order_by(SourceDocument.created_at.desc()).limit(200)
    ).all()
    return [_document_out(item) for item in items]


@app.post("/api/documents/upload", response_model=DocumentOut)
async def upload_document(file: UploadFile = File(...), db: Session = Depends(get_db)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in {".pdf", ".xlsx", ".csv", ".dbf", ".zip"}:
        raise HTTPException(415, "Поддерживаются PDF, XLSX, CSV, DBF и ZIP")
    temp = Storage().temporary_path(suffix)
    size = 0
    maximum = settings.max_file_mb * 1024 * 1024
    with temp.open("wb") as output:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > maximum:
                raise HTTPException(413, "Файл превышает лимит")
            output.write(chunk)
    try:
        item = DocumentService(db).ingest_path(temp, file.filename or "Документ")
        return _document_out(item)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/documents/discover", response_model=RunCreated)
def discover_documents(payload: DocumentDiscover, db: Session = Depends(get_db)):
    if payload.idempotency_key:
        existing = db.scalar(
            select(AnalysisRun).where(AnalysisRun.idempotency_key == payload.idempotency_key)
        )
        if existing:
            return RunCreated(run_id=existing.id)
    thread = Thread(title=f"Поиск отчетности: {payload.bank_query}")
    db.add(thread)
    db.flush()
    text = f"Найди {payload.document_type or 'МСФО или РСБУ'} банка {payload.bank_query} {payload.period or ''}, скачай наиболее релевантный официальный документ и сообщи результат."
    message = Message(thread_id=thread.id, role="user", content=text)
    db.add(message)
    db.flush()
    run = AnalysisRun(
        thread_id=thread.id,
        message_id=message.id,
        task_type="document_discovery",
        idempotency_key=payload.idempotency_key,
    )
    db.add(run)
    db.commit()
    dispatch_task(run_agent, run.id)
    return RunCreated(run_id=run.id)


def _document_file(db: Session, document_id: str):
    document = db.get(SourceDocument, document_id)
    if not document or not document.versions:
        raise HTTPException(404, "Document not found")
    version = sorted(document.versions, key=lambda item: item.created_at)[-1]
    path = Path(version.storage_path)
    if not path.exists():
        raise HTTPException(410, "Stored file is missing")
    return document, path, version.mime_type


def _document_out(document: SourceDocument) -> DocumentOut:
    version = max(document.versions, key=lambda item: item.created_at) if document.versions else None
    mime_type = version.mime_type if version else None
    return DocumentOut(
        id=document.id,
        title=document.title,
        document_type=document.document_type,
        reporting_standard=document.reporting_standard,
        source_url=document.source_url,
        source_tier=document.source_tier,
        status=document.status,
        mime_type=mime_type,
        size_bytes=version.size_bytes if version else None,
        previewable=mime_type == "application/pdf",
        created_at=document.created_at,
    )


@app.get("/api/documents/{document_id}", response_model=DocumentOut)
def get_document(document_id: str, db: Session = Depends(get_db)):
    item = db.get(SourceDocument, document_id)
    if not item:
        raise HTTPException(404, "Document not found")
    return _document_out(item)


@app.get("/api/documents/{document_id}/preview")
def preview_document(document_id: str, db: Session = Depends(get_db)):
    _, path, mime = _document_file(db, document_id)
    if mime != "application/pdf":
        raise HTTPException(415, "Предпросмотр доступен только для PDF")
    return FileResponse(
        path,
        media_type=mime,
        headers={
            "Content-Disposition": "inline",
            "Content-Security-Policy": "frame-ancestors 'self'",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, no-store",
        },
    )


@app.get("/api/documents/{document_id}/download")
def download_document(document_id: str, db: Session = Depends(get_db)):
    document, path, mime = _document_file(db, document_id)
    return FileResponse(path, media_type=mime, filename=path.name)


@app.delete("/api/documents/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    item = db.get(SourceDocument, document_id)
    if not item:
        raise HTTPException(404, "Document not found")
    Storage().remove_document(item.id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@app.post("/api/articles/search", response_model=list[ArticleOut])
def search_articles(payload: ArticleSearch):
    query = " ".join(part for part in (payload.bank, payload.query) if part)
    return [
        ArticleOut(**item.__dict__)
        for item in BrowserClient().search_articles(
            query, payload.limit, payload.domains, payload.date_from, payload.date_to
        )
    ]


@app.get("/api/calendar", response_model=list[CalendarOut])
def list_calendar(
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    bank: str | None = None,
    event_type: str | None = Query(None, alias="type"),
    status: str | None = None,
    db: Session = Depends(get_db),
):
    query = select(CalendarEvent).order_by(CalendarEvent.starts_at)
    if date_from:
        query = query.where(CalendarEvent.starts_at >= date_from)
    if date_to:
        query = query.where(CalendarEvent.starts_at <= date_to)
    if bank:
        query = query.where(CalendarEvent.bank_reg_number == bank)
    if event_type:
        query = query.where(CalendarEvent.event_type == event_type)
    if status:
        query = query.where(CalendarEvent.status == status)
    return [
        CalendarOut(
            id=item.id,
            title=item.title,
            event_type=item.event_type,
            starts_at=item.starts_at,
            ends_at=item.ends_at,
            status=item.status,
            confidence=item.confidence,
            source_url=item.source_url,
            bank_name=item.bank.name if item.bank else None,
        )
        for item in db.scalars(query.limit(1000)).all()
    ]


@app.get("/api/calendar.ics")
def calendar_ics(db: Session = Depends(get_db)):
    events = list(db.scalars(select(CalendarEvent).order_by(CalendarEvent.starts_at)).all())
    return Response(
        CalendarService(db).to_ics(events),
        media_type="text/calendar",
        headers={"Content-Disposition": "attachment; filename=bank-reporter.ics"},
    )


@app.post("/api/calendar/sync")
def trigger_calendar_sync():
    try:
        task = dispatch_task(sync_calendar)
        return {"task_id": task.id, "status": "queued"}
    except Exception as exc:
        raise HTTPException(503, f"Очередь недоступна: {exc}") from exc


@app.post("/api/reports", response_model=ReportOut)
def create_report(
    payload: ReportCreate,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
    db: Session = Depends(get_db),
):
    key = idempotency_key or payload.idempotency_key
    if key:
        existing = db.scalar(select(Report).where(Report.idempotency_key == key))
        if existing:
            return existing
    missing = [item for item in payload.document_ids if not db.get(SourceDocument, item)]
    if missing:
        raise HTTPException(404, f"Документы не найдены: {missing}")
    report = Report(
        title=payload.title,
        report_kind=payload.report_kind,
        document_ids=payload.document_ids,
        idempotency_key=key,
    )
    db.add(report)
    db.commit()
    try:
        dispatch_task(create_report_task, report.id, payload.question, payload.output_formats)
    except Exception as exc:
        report.status = "failed"
        report.summary = f"Очередь недоступна: {exc}"
        db.commit()
    return report


@app.get("/api/reports", response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db)):
    return list(db.scalars(select(Report).order_by(Report.created_at.desc()).limit(200)).unique().all())


@app.post("/api/reports/{report_id}/rebuild", response_model=ReportOut)
def rebuild_report(report_id: str, db: Session = Depends(get_db)):
    item = db.get(Report, report_id)
    if not item:
        raise HTTPException(404, "Report not found")
    if item.status in {"queued", "processing"}:
        raise HTTPException(409, "Отчет уже формируется")
    output_formats = sorted({artifact.format for artifact in item.artifacts} | {"html"})
    item.status = "queued"
    db.commit()
    try:
        dispatch_task(
            create_report_task,
            item.id,
            "Пересобери финансовый анализ. Для каждого сопоставимого показателя явно покажи "
            "предыдущий и текущий периоды, абсолютное значение и процентную динамику.",
            output_formats,
        )
    except Exception as exc:
        item.status = "failed"
        item.summary = f"Очередь недоступна: {exc}"
        db.commit()
    return item


@app.get("/api/reports/{report_id}", response_model=ReportOut)
def get_report(report_id: str, db: Session = Depends(get_db)):
    item = db.get(Report, report_id)
    if not item:
        raise HTTPException(404, "Report not found")
    return item


@app.delete("/api/reports/{report_id}")
def delete_report(report_id: str, db: Session = Depends(get_db)):
    item = db.get(Report, report_id)
    if not item:
        raise HTTPException(404, "Report not found")
    if item.status in {"queued", "processing"}:
        raise HTTPException(409, "Дождитесь завершения создания отчета")
    Storage().remove_report(item.id)
    db.delete(item)
    db.commit()
    return Response(status_code=204)


@app.get("/api/reports/{report_id}/preview")
def preview_report(report_id: str, db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    artifact = db.scalar(
        select(Artifact).where(Artifact.report_id == report_id, Artifact.format == "html")
    )
    if not artifact:
        raise HTTPException(409, "HTML preview is not ready")
    path = Path(artifact.storage_path)
    if not path.exists():
        raise HTTPException(410, "Preview file is missing")
    return FileResponse(
        path,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": "inline",
            "Content-Security-Policy": (
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:; "
                "font-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
            ),
            "X-Frame-Options": "SAMEORIGIN",
            "Cache-Control": "private, no-store",
        },
    )


@app.get("/api/artifacts/{artifact_id}/download")
def download_artifact(artifact_id: str, db: Session = Depends(get_db)):
    item = db.get(Artifact, artifact_id)
    if not item:
        raise HTTPException(404, "Artifact not found")
    path = Path(item.storage_path)
    if not path.exists():
        raise HTTPException(410, "Artifact file is missing")
    return FileResponse(path, media_type=item.mime_type, filename=path.name)
