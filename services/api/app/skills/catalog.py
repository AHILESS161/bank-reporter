from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, Field

from .contracts import ModelPolicy, SideEffects, SkillManifest, SkillTransport
from .registry import SkillHandler, SkillRegistry


ORCHESTRATOR_MODEL = "deepseek/deepseek-v4.1-flash"
FINANCE_MODEL = "inclusionai/ling-3.0-flash-fin"


class SkillHost(Protocol):
    def tool_resolve_bank(self, query: str) -> Any: ...

    def tool_fetch_cbr_form(
        self, bank_reg_number: str, form: int, date_from: str, date_to: str
    ) -> Any: ...

    def tool_discover_documents(
        self, bank_reg_number: str, document_type: str = "", period: str = ""
    ) -> Any: ...

    def tool_download_document(
        self,
        url: str,
        title: str,
        bank_reg_number: str | None = None,
        document_type: str = "other",
    ) -> Any: ...

    def tool_search_articles(self, query: str, limit: int = 20) -> Any: ...

    def tool_read_article(self, url: str, title: str = "") -> Any: ...

    def tool_list_documents(self, bank_reg_number: str | None = None) -> Any: ...

    def tool_query_financial_facts(self, bank_reg_number: str, limit: int = 100) -> Any: ...

    def tool_read_document(self, document_id: str, max_chars: int = 60_000) -> Any: ...

    def tool_create_report(
        self,
        document_ids: list[str],
        title: str,
        question: str,
        report_kind: str = "financial",
    ) -> Any: ...


class ResolveBankInput(BaseModel):
    query: str = Field(min_length=2, max_length=300)


class FetchCBRFormInput(BaseModel):
    bank_reg_number: str = Field(min_length=1, max_length=20)
    form: int = Field(ge=101, le=102)
    date_from: str
    date_to: str


class DiscoverDocumentsInput(BaseModel):
    bank_reg_number: str = Field(min_length=1, max_length=20)
    document_type: str = Field("", max_length=200)
    period: str = Field("", max_length=100)


class DownloadDocumentInput(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    title: str = Field(min_length=1, max_length=600)
    bank_reg_number: str | None = Field(None, max_length=20)
    document_type: str = Field("other", max_length=50)


class SearchArticlesInput(BaseModel):
    query: str = Field(min_length=2, max_length=500)
    limit: int = Field(20, ge=1, le=30)


class ReadArticleInput(BaseModel):
    url: str = Field(min_length=8, max_length=2000)
    title: str = Field("", max_length=600)


class ListDocumentsInput(BaseModel):
    bank_reg_number: str | None = Field(None, max_length=20)


class QueryFinancialFactsInput(BaseModel):
    bank_reg_number: str = Field(min_length=1, max_length=20)
    limit: int = Field(100, ge=1, le=200)


class ReadDocumentInput(BaseModel):
    document_id: str = Field(min_length=1, max_length=36)
    max_chars: int = Field(60_000, ge=1_000, le=100_000)


class CreateReportInput(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=20)
    title: str = Field(min_length=1, max_length=500)
    question: str = Field(min_length=1, max_length=5_000)
    report_kind: str = Field("financial", pattern=r"^(financial|comparison|brief)$")


def _manifest(
    skill_id: str,
    title: str,
    description: str,
    category: str,
    *,
    transport: SkillTransport = SkillTransport.LOCAL,
    side_effects: SideEffects = SideEffects.READ_ONLY,
    permissions: list[str] | None = None,
    timeout_seconds: int = 60,
    model_policy: ModelPolicy | None = None,
) -> SkillManifest:
    return SkillManifest(
        id=skill_id,
        title=title,
        description=description,
        category=category,
        transport=transport,
        side_effects=side_effects,
        permissions=permissions or [],
        timeout_seconds=timeout_seconds,
        model_policy=model_policy,
    )


SKILL_DEFINITIONS: tuple[tuple[SkillManifest, type[BaseModel], str], ...] = (
    (
        _manifest(
            "resolve_bank",
            "Определить банк",
            "Найти банк в официальном справочнике ЦБ по названию и получить регистрационный номер.",
            "research",
            transport=SkillTransport.SERVICE,
            permissions=["network:cbr", "database:banks:write"],
        ),
        ResolveBankInput,
        "tool_resolve_bank",
    ),
    (
        _manifest(
            "discover_documents",
            "Найти отчётность",
            "Найти ссылки на отчётность, сначала на официальном сайте банка, затем через безопасный браузерный поиск.",
            "research",
            transport=SkillTransport.SERVICE,
            permissions=["network:http_read", "browser:search_read"],
            timeout_seconds=120,
        ),
        DiscoverDocumentsInput,
        "tool_discover_documents",
    ),
    (
        _manifest(
            "download_document",
            "Скачать документ",
            "Скачать публичный документ, проверить его и сохранить неизменяемую локальную версию.",
            "documents",
            transport=SkillTransport.SERVICE,
            side_effects=SideEffects.LOCAL_WRITE,
            permissions=["network:http_read", "storage:documents:write"],
            timeout_seconds=180,
        ),
        DownloadDocumentInput,
        "tool_download_document",
    ),
    (
        _manifest(
            "fetch_cbr_form",
            "Загрузить форму ЦБ",
            "Получить официальную форму ЦБ 101 или 102 за период и сохранить оригинал.",
            "documents",
            transport=SkillTransport.SERVICE,
            side_effects=SideEffects.LOCAL_WRITE,
            permissions=["network:cbr", "storage:documents:write"],
            timeout_seconds=120,
        ),
        FetchCBRFormInput,
        "tool_fetch_cbr_form",
    ),
    (
        _manifest(
            "search_articles",
            "Искать публикации",
            "Найти официальные публикации и профильные статьи в открытом вебе, включая поиск по домену.",
            "research",
            transport=SkillTransport.SERVICE,
            permissions=["browser:search_read"],
            timeout_seconds=120,
        ),
        SearchArticlesInput,
        "tool_search_articles",
    ),
    (
        _manifest(
            "read_article",
            "Прочитать публикацию",
            "Извлечь основное содержимое публичной HTML-страницы как недоверенные данные.",
            "research",
            transport=SkillTransport.SERVICE,
            permissions=["browser:navigate_read"],
            timeout_seconds=90,
        ),
        ReadArticleInput,
        "tool_read_article",
    ),
    (
        _manifest(
            "list_documents",
            "Получить библиотеку",
            "Получить ранее загруженные документы из локальной библиотеки.",
            "documents",
            permissions=["database:documents:read"],
        ),
        ListDocumentsInput,
        "tool_list_documents",
    ),
    (
        _manifest(
            "query_financial_facts",
            "Получить финансовые факты",
            "Получить нормализованные Decimal-факты с периодами и точными координатами первоисточника.",
            "analysis",
            permissions=["database:facts:read"],
        ),
        QueryFinancialFactsInput,
        "tool_query_financial_facts",
    ),
    (
        _manifest(
            "read_document",
            "Прочитать документ",
            "Прочитать извлечённый текст документа с маркерами страниц, листов и ячеек.",
            "documents",
            permissions=["storage:documents:read"],
        ),
        ReadDocumentInput,
        "tool_read_document",
    ),
    (
        _manifest(
            "create_report",
            "Собрать аналитический отчёт",
            "Проверить факты, выполнить детерминированные расчёты и собрать HTML/PDF/PNG/XLSX/CSV только по явному запросу анализа.",
            "reporting",
            side_effects=SideEffects.LOCAL_WRITE,
            permissions=["database:facts:read", "storage:artifacts:write", "browser:render"],
            timeout_seconds=900,
            model_policy=ModelPolicy(
                primary=FINANCE_MODEL,
                fallback=ORCHESTRATOR_MODEL,
                max_attempts=2,
            ),
        ),
        CreateReportInput,
        "tool_create_report",
    ),
)


def _bound_handler(host: SkillHost | None, method_name: str) -> SkillHandler | None:
    if host is None:
        return None
    method = getattr(host, method_name)

    def execute(payload: BaseModel) -> Any:
        return method(**payload.model_dump(exclude_none=True))

    return execute


def build_skill_registry(host: SkillHost | None = None) -> SkillRegistry:
    registry = SkillRegistry()
    for manifest, input_model, method_name in SKILL_DEFINITIONS:
        registry.register(manifest, input_model, _bound_handler(host, method_name))
    return registry
