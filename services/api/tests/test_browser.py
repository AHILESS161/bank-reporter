import json

from app.services.browser import Article, BrowserClient


def test_structured_search_filters_unrelated_and_deduplicates():
    client = BrowserClient()
    results = client._parse_structured(
        [
            {"title": "Сбер опубликовал финансовые результаты", "url": "https://rbc.ru/sber-results"},
            {"title": "Сбер опубликовал финансовые результаты", "url": "https://rbc.ru/sber-results?utm=x"},
            {"title": "Новости другого рынка", "url": "https://example.com/unrelated"},
        ],
        "Сбер финансовые результаты",
        set(),
        set(),
        [],
    )
    assert len(results) == 1
    assert results[0].trust_tier == "trusted_media"


def test_query_tokens_ignore_generic_search_words():
    assert BrowserClient._query_tokens("Статьи и новости про банк Сбер") == {"статьи", "сбер"}


def test_bing_rss_is_parsed_as_inert_structured_data():
    raw = json.dumps(
        {
            "data": {
                "content": """<rss><channel><item><title>Сбер опубликовал отчетность</title>
                <link>https://rbc.ru/finances/sber</link>
                <description>Краткое описание результата.</description></item></channel></rss>"""
            }
        }
    )
    results = BrowserClient()._parse_search(raw, set(), set(), [], "Сбер отчетность")
    assert results[0].title == "Сбер опубликовал отчетность"
    assert results[0].excerpt == "Краткое описание результата."


def test_article_enrichment_is_bounded(monkeypatch):
    enriched: list[str] = []
    monkeypatch.setattr(BrowserClient, "_enrich", lambda article: enriched.append(article.url))
    articles = [
        Article(str(index), f"https://example.com/{index}", "example.com", "", "other", 1)
        for index in range(12)
    ]

    BrowserClient._enrich_many(articles)

    assert len(enriched) == 8
