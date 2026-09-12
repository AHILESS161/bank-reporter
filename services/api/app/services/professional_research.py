from __future__ import annotations

from collections.abc import Iterable
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .browser import BrowserClient
from .network import public_get
from .security import domain_of


PROFESSIONAL_REPORT_DOMAINS = (
    "acra-ratings.ru",
    "raexpert.ru",
    "cbr.ru",
)
PROFESSIONAL_MENTIONS = ("эксперт ра", "акра", "рейтинговое агентство", "банк россии")


class ProfessionalResearchService:
    """Find bounded public expert context without treating it as primary figures."""

    def __init__(self, browser: BrowserClient | None = None) -> None:
        self.browser = browser or BrowserClient()

    def collect(
        self,
        entities: Iterable[str],
        question: str = "",
        *,
        limit: int = 4,
    ) -> list[dict]:
        names = [str(item).strip() for item in entities if str(item).strip()]
        if not names or limit <= 0:
            return []
        subject = " ".join(dict.fromkeys(names[:2]))
        words = [
            word
            for word in re.findall(r"[а-яёa-z]+", subject.casefold())
            if word not in {"пао", "ао", "ооо", "зао", "кб", "акб"}
        ]
        acronym = "".join(word[0] for word in words) if 2 <= len(words) <= 5 else ""
        subject_query = f"{subject} {acronym}".strip()
        topic = "кредитный рейтинг финансовый профиль аналитический обзор"
        if any(token in question.casefold() for token in ("ликвид", "капитал", "кредит", "риск")):
            topic += " риски капитал ликвидность качество активов"

        found: list[dict] = []
        seen: set[str] = set()
        for domain in PROFESSIONAL_REPORT_DOMAINS:
            if len(found) >= limit:
                break
            query = f"site:{domain} {subject_query} {topic}"
            try:
                results = self.browser.search_articles(query, limit=2, domains=[domain])
            except Exception:
                continue
            for article in results:
                if article.url in seen:
                    continue
                seen.add(article.url)
                found.append(
                    {
                        "id": f"P{len(found) + 1}",
                        "title": article.title or article.source,
                        "url": article.url,
                        "publisher": article.source,
                        "published_at": article.published_at.isoformat()
                        if article.published_at
                        else None,
                        "excerpt": article.excerpt[:1200],
                        "role": "professional_context",
                    }
                )
                if len(found) >= limit:
                    break
        if not found:
            # Search engines sometimes surface a public rating action through a
            # reputable newswire while hiding the agency page behind dynamic
            # navigation. Keep such a result only when the title/excerpt clearly
            # attributes it to a rating agency.
            try:
                fallback = self.browser.search_articles(
                    f"{subject_query} рейтинг Эксперт РА АКРА", limit=min(limit * 2, 8)
                )
            except Exception:
                fallback = []
            for article in fallback:
                haystack = f"{article.title} {article.excerpt}".casefold()
                if not any(marker in haystack for marker in PROFESSIONAL_MENTIONS):
                    continue
                direct = self._direct_professional_source(article.url)
                url = direct.get("url") if direct else article.url
                if url in seen:
                    continue
                seen.add(url)
                found.append(
                    {
                        "id": f"P{len(found) + 1}",
                        "title": (
                            str(direct.get("title") or article.title or article.source)
                            if direct
                            else article.title or article.source
                        ),
                        "url": url,
                        "publisher": domain_of(url),
                        "published_at": article.published_at.isoformat()
                        if article.published_at
                        else None,
                        "excerpt": (
                            str(direct.get("content") or article.excerpt)[:1200]
                            if direct
                            else article.excerpt[:1200]
                        ),
                        "role": "professional_context",
                    }
                )
                if len(found) >= limit:
                    break
        return found

    def _direct_professional_source(self, article_url: str) -> dict | None:
        try:
            final_url, content = public_get(article_url, timeout=20, max_bytes=5 * 1024 * 1024)
            soup = BeautifulSoup(content.decode("utf-8", errors="replace"), "html.parser")
            for anchor in soup.select("a[href]"):
                candidate = urljoin(final_url, str(anchor.get("href") or ""))
                if not candidate.startswith(("http://", "https://")):
                    continue
                domain = domain_of(candidate)
                if not any(
                    domain == allowed or domain.endswith(f".{allowed}")
                    for allowed in PROFESSIONAL_REPORT_DOMAINS
                ):
                    continue
                try:
                    result = self.browser.read_article(candidate)
                    if result.get("url"):
                        return result
                except Exception:
                    publisher = {
                        "raexpert.ru": "Эксперт РА",
                        "acra-ratings.ru": "АКРА",
                        "cbr.ru": "Банк России",
                    }.get(domain, domain)
                    return {
                        "url": candidate,
                        "title": f"Профессиональный обзор · {publisher}",
                        "content": "",
                    }
        except Exception:
            return None
        return None
