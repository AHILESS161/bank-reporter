from types import SimpleNamespace

from app.services.agent import (
    OFFICIAL_DISCLOSURE_ENTRYPOINTS,
    SYSTEM,
    AgentService,
    ToolCallGuard,
    requests_analysis,
    requests_download,
    sanitize_agent_answer,
)


def test_document_search_does_not_implicitly_request_analysis():
    assert requests_analysis("Найди и скачай МСФО МКБ за 2025 год") is False
    assert requests_analysis("Найди официальный годовой отчет банка") is False
    assert requests_analysis("Найди отчет, анализ не делай") is False


def test_explicit_analysis_requests_are_detected():
    assert requests_analysis("Проанализируй этот PDF") is True
    assert requests_analysis("Сравни прибыль за два периода") is True
    assert requests_analysis("Сделай аналитический отчет и график") is True


def test_explicit_download_requests_are_detected():
    assert requests_download("\u041d\u0430\u0439\u0434\u0438 \u0438 \u0441\u043a\u0430\u0447\u0430\u0439 \u041c\u0421\u0424\u041e \u0412\u0422\u0411") is True
    assert requests_download("\u0421\u043e\u0445\u0440\u0430\u043d\u0438 \u043e\u0444\u0438\u0446\u0438\u0430\u043b\u044c\u043d\u044b\u0439 PDF") is True
    assert requests_download("\u041a\u0430\u043a\u0430\u044f \u043f\u043e\u0441\u043b\u0435\u0434\u043d\u044f\u044f \u043e\u0442\u0447\u0435\u0442\u043d\u043e\u0441\u0442\u044c?") is False


def test_official_document_candidate_stops_non_download_research():
    agent = AgentService.__new__(AgentService)
    agent.analysis_requested = False
    agent.download_requested = False
    result = [{"title": "IFRS consolidated financial statements 2025", "url": "https://bank.test/ifrs.pdf"}]
    assert agent._evidence_is_sufficient("discover_documents", result) is True
    assert agent._evidence_is_sufficient("search_articles", result) is False


def test_presentation_does_not_stop_document_research():
    agent = AgentService.__new__(AgentService)
    agent.analysis_requested = False
    agent.download_requested = False
    result = [{"title": "IFRS presentation 2025", "url": "https://bank.test/slides.pdf"}]
    assert agent._evidence_is_sufficient("discover_documents", result) is False


def test_tool_guard_blocks_duplicate_and_caps_search_variations():
    guard = ToolCallGuard({"search_articles": 2})
    assert guard.reject_reason("search_articles", {"query": "банк МСФО"}) is None
    assert "уже выполнялся" in guard.reject_reason(
        "search_articles", {"query": "банк МСФО"}
    )
    assert guard.reject_reason("search_articles", {"query": "банк IFRS"}) is None
    assert "Лимит вызовов" in guard.reject_reason(
        "search_articles", {"query": "банк отчетность"}
    )


def test_tbank_has_current_official_disclosure_entrypoints():
    urls = OFFICIAL_DISCLOSURE_ENTRYPOINTS["2673"]
    assert "https://www.tbank.ru/about/investors/11/" in urls
    assert "https://t-technologies.ru/results/" in urls


def test_major_banks_have_direct_reporting_entrypoints():
    assert OFFICIAL_DISCLOSURE_ENTRYPOINTS["1000"][0].endswith("/ir/statements/results/")
    assert OFFICIAL_DISCLOSURE_ENTRYPOINTS["3251"][0].endswith("/bank/investors/ifrs")
    assert any(
        item.endswith("/reports-conclusion/msfo")
        for item in OFFICIAL_DISCLOSURE_ENTRYPOINTS["3349"]
    )
    assert OFFICIAL_DISCLOSURE_ENTRYPOINTS["1978"][0].endswith("/reports/ifrs")
    assert OFFICIAL_DISCLOSURE_ENTRYPOINTS["2312"][0].endswith("/information/msfo/")
    assert any("sectionId=325" in item for item in OFFICIAL_DISCLOSURE_ENTRYPOINTS["354"])
    assert all("79789" not in item for item in OFFICIAL_DISCLOSURE_ENTRYPOINTS["354"])


def test_forced_finalization_calls_model_without_tools():
    calls: list[tuple[list[dict], object]] = []

    class Models:
        def chat(self, messages, tools=None):
            calls.append((messages, tools))
            return SimpleNamespace(content="Найден последний подтвержденный отчет.")

    agent = AgentService.__new__(AgentService)
    agent.models = Models()
    agent.sources = []
    agent._event = lambda *_: None
    agent._complete = lambda _run, answer, status="completed": (answer, status)

    answer, status = agent._finalize_from_evidence(object(), [{"role": "user", "content": "x"}])

    assert answer == "Найден последний подтвержденный отчет."
    assert status == "partial"
    assert calls[0][1] is None
    assert "обязательный финальный шаг" in calls[0][0][-1]["content"].casefold()


def test_forced_finalization_has_deterministic_fallback():
    class Models:
        def chat(self, *_args, **_kwargs):
            raise RuntimeError("provider unavailable")

    agent = AgentService.__new__(AgentService)
    agent.models = Models()
    agent.sources = [{"message": "Официальная отчетность", "url": "https://example.com"}]
    agent._event = lambda *_: None
    agent._complete = lambda _run, answer, status="completed": (answer, status)

    answer, status = agent._finalize_from_evidence(object(), [])

    assert "Официальная отчетность" in answer
    assert "лимит агентских шагов" not in answer.casefold()
    assert status == "partial"


def test_discovery_keeps_web_capacity_for_fallback_search():
    agent = AgentService.__new__(AgentService)
    agent.settings = SimpleNamespace(max_web_pages=25)

    agent.pages = 0
    assert agent._discovery_page_limit() == 10
    agent.pages = 10
    assert agent._discovery_page_limit() == 20
    agent.pages = 20
    assert agent._discovery_page_limit() == 21


def test_page_reservation_never_overflows_or_returns_internal_error():
    agent = AgentService.__new__(AgentService)
    agent.settings = SimpleNamespace(max_web_pages=25)
    agent.pages = 24
    events: list[tuple[str, dict]] = []
    agent._event = lambda kind, payload: events.append((kind, payload))

    assert agent._reserve_pages(2) is False
    assert agent.pages == 24
    assert "лимит" not in events[0][1]["message"].casefold()
    assert agent._reserve_pages(1) is True
    assert agent.pages == 25


def test_agent_prompt_forbids_exposing_internal_search_limits():
    prompt = SYSTEM.casefold()
    assert "никогда не упоминай внутренние лимиты" in prompt
    assert "тексты служебных ошибок" in prompt


def test_document_discovery_cannot_read_unfiltered_library_before_bank_resolution():
    agent = AgentService.__new__(AgentService)
    agent.active_workflow_id = "document_discovery"
    agent.resolved_bank_numbers = set()

    assert agent.tool_list_documents() == []


def test_workflow_dependencies_block_fallback_until_official_discovery():
    agent = AgentService.__new__(AgentService)
    agent.workflow_required_dependencies = {
        "search_articles": {"discover_documents"},
    }
    agent.completed_skill_ids = {"resolve_bank"}

    assert agent._missing_tool_dependencies("search_articles") == ["discover_documents"]
    agent.completed_skill_ids.add("discover_documents")
    assert agent._missing_tool_dependencies("search_articles") == []


def test_user_answer_replaces_internal_page_limit_message():
    answer = sanitize_agent_answer(
        "## Итог\n\nИсточник недоступен (исчерпан лимит обращений к страницам). "
        "Это не означает отсутствие публикации."
    )

    assert "лимит" not in answer.casefold()
    assert "Подтвердить результат по доступным официальным источникам не удалось." in answer
