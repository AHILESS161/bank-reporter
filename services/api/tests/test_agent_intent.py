from app.services.agent import requests_analysis


def test_document_search_does_not_implicitly_request_analysis():
    assert requests_analysis("Найди и скачай МСФО МКБ за 2025 год") is False
    assert requests_analysis("Найди официальный годовой отчет банка") is False
    assert requests_analysis("Найди отчет, анализ не делай") is False


def test_explicit_analysis_requests_are_detected():
    assert requests_analysis("Проанализируй этот PDF") is True
    assert requests_analysis("Сравни прибыль за два периода") is True
    assert requests_analysis("Сделай аналитический отчет и график") is True
