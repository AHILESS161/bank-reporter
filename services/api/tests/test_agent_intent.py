from types import SimpleNamespace

from app.services.agent import (
    OFFICIAL_DISCLOSURE_ENTRYPOINTS,
    AgentService,
    ToolCallGuard,
    requests_analysis,
)


def test_document_search_does_not_implicitly_request_analysis():
    assert requests_analysis("Найди и скачай МСФО МКБ за 2025 год") is False
    assert requests_analysis("Найди официальный годовой отчет банка") is False
    assert requests_analysis("Найди отчет, анализ не делай") is False


def test_explicit_analysis_requests_are_detected():
    assert requests_analysis("Проанализируй этот PDF") is True
    assert requests_analysis("Сравни прибыль за два периода") is True
    assert requests_analysis("Сделай аналитический отчет и график") is True


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
