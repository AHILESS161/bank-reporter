from datetime import datetime

from app.services.browser import Article
from app.services.professional_research import ProfessionalResearchService


class BrowserStub:
    def search_articles(self, query: str, limit: int, domains: list[str]):
        domain = domains[0]
        return [
            Article(
                title=f"Обзор {domain}",
                url=f"https://{domain}/bank-review",
                source=domain,
                excerpt="Публичный аналитический обзор банка.",
                trust_tier="other",
                score=50,
                published_at=datetime(2026, 1, 10),
            )
        ]


def test_professional_research_returns_bounded_attributed_context():
    rows = ProfessionalResearchService(BrowserStub()).collect(["МКБ"], "динамика прибыли", limit=2)
    assert [item["id"] for item in rows] == ["P1", "P2"]
    assert rows[0]["role"] == "professional_context"
    assert rows[0]["url"].startswith("https://")
    assert rows[0]["excerpt"] == "Публичный аналитический обзор банка."
