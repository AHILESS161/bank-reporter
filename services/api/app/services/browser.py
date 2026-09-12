import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qs, unquote, urlparse

import httpx
import trafilatura
from bs4 import BeautifulSoup

from ..config import get_settings
from .security import canonical_url, domain_of, normalized_title, validate_public_url
from .network import public_get


@dataclass
class Article:
    title: str
    url: str
    source: str
    excerpt: str
    trust_tier: str
    score: float
    author: str | None = None
    published_at: datetime | None = None
    language: str | None = None


class BrowserClient:
    def __init__(self):
        self.settings = get_settings()

    def read(self, url: str) -> str:
        validate_public_url(url)
        with httpx.Client(timeout=130) as client:
            response = client.post(f"{self.settings.browser_service_url}/read", json={"url": url})
            response.raise_for_status()
            return response.json().get("content", "")

    def search_articles(
        self,
        query: str,
        limit: int = 20,
        domains: list[str] | None = None,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[Article]:
        search_query = query
        if date_from:
            search_query += f" after:{date_from.isoformat()}"
        if date_to:
            search_query += f" before:{date_to.isoformat()}"
        seen_urls: set[str] = set()
        seen_titles: set[str] = set()
        articles: list[Article] = []
        for engine in ("yandex", "bing"):
            try:
                with httpx.Client(timeout=130) as client:
                    response = client.post(
                        f"{self.settings.browser_service_url}/search",
                        json={"query": search_query, "engine": engine},
                    )
                    response.raise_for_status()
                    payload = response.json()
                articles.extend(
                    self._parse_structured(
                        payload.get("results", []), query, seen_urls, seen_titles, domains or []
                    )
                )
                if not payload.get("results") and payload.get("content"):
                    articles.extend(
                        self._parse_search(
                            payload["content"], seen_urls, seen_titles, domains or [], query
                        )
                    )
            except Exception:
                continue
            if len(articles) >= limit:
                break
        ordered = sorted(articles, key=lambda item: item.score, reverse=True)[: min(limit, 25)]
        for article in ordered:
            self._enrich(article)
        query_tokens = self._query_tokens(query)
        return [
            item
            for item in ordered
            if self._is_relevant(item.title, item.url, query_tokens)
            and (not date_from or not item.published_at or item.published_at.date() >= date_from)
            and (not date_to or not item.published_at or item.published_at.date() <= date_to)
        ][:limit]

    def _parse_structured(
        self,
        items: list[dict],
        query: str,
        seen_urls: set[str],
        seen_titles: set[str],
        domains: list[str],
    ) -> list[Article]:
        tokens = self._query_tokens(query)
        results: list[Article] = []
        for item in items:
            title = str(item.get("title", "")).strip()[:300]
            url = canonical_url(self._search_target(str(item.get("url", ""))))
            try:
                validate_public_url(url)
            except ValueError:
                continue
            domain = domain_of(url)
            if domains and not any(domain == value or domain.endswith(f".{value}") for value in domains):
                continue
            title_key = normalized_title(title)
            if not title_key or url in seen_urls or title_key in seen_titles:
                continue
            if not self._is_relevant(title, url, tokens):
                continue
            seen_urls.add(url)
            seen_titles.add(title_key)
            official = domain.endswith(("cbr.ru", "minfin.gov.ru"))
            trusted = any(
                domain == value or domain.endswith(f".{value}")
                for value in self.settings.trusted_domains
            )
            tier = "official" if official else "trusted_media" if trusted else "other"
            matches = sum(token in f"{title} {url}".casefold() for token in tokens)
            score = (100.0 if official else 80.0 if trusted else 50.0) + matches * 2
            results.append(
                Article(
                    title,
                    url,
                    domain,
                    str(item.get("excerpt", ""))[:500],
                    tier,
                    score,
                    published_at=item.get("published_at"),
                )
            )
        return results

    def _parse_search(
        self,
        raw: str,
        seen_urls: set[str],
        seen_titles: set[str],
        domains: list[str],
        query: str = "",
    ) -> list[Article]:
        try:
            data = json.loads(raw)
            content = data.get("data", {}).get("content", "") if isinstance(data, dict) else ""
            if "<rss" in content:
                feed = BeautifulSoup(content, "xml")
                structured = [
                    {
                        "title": item.title.get_text(" ", strip=True),
                        "url": item.link.get_text(strip=True),
                        "excerpt": item.description.get_text(" ", strip=True)
                        if item.description
                        else "",
                        "published_at": self._feed_date(
                            item.pubDate.get_text(strip=True) if item.pubDate else ""
                        ),
                    }
                    for item in feed.find_all("item")
                    if item.title and item.link
                ]
                return self._parse_structured(
                    structured, query, seen_urls, seen_titles, domains
                )
            text = json.dumps(data, ensure_ascii=False)
        except json.JSONDecodeError:
            text = raw
        urls = re.findall(r"https?://[^\s\]\[<>{}\"']+", text)
        results: list[Article] = []
        tokens = self._query_tokens(query)
        for url in urls:
            url = canonical_url(url.rstrip(".,;)"))
            try:
                validate_public_url(url)
            except ValueError:
                continue
            domain = domain_of(url)
            if domain.endswith(("yandex.ru", "yandex.com", "bing.com", "microsoft.com")):
                continue
            if domains and not any(domain == value or domain.endswith(f".{value}") for value in domains):
                continue
            title = urlparse(url).path.strip("/").replace("-", " ").replace("_", " ") or domain
            title_key = normalized_title(title)
            if url in seen_urls or title_key in seen_titles:
                continue
            if not self._is_relevant(title, url, tokens):
                continue
            seen_urls.add(url)
            seen_titles.add(title_key)
            official = domain.endswith(("cbr.ru", "minfin.gov.ru"))
            trusted = any(
                domain == item or domain.endswith(f".{item}") for item in self.settings.trusted_domains
            )
            tier = "official" if official else "trusted_media" if trusted else "other"
            score = 100.0 if official else 80.0 if trusted else 50.0
            results.append(
                Article(title=title[:300], url=url, source=domain, excerpt="", trust_tier=tier, score=score)
            )
        return results

    @staticmethod
    def _search_target(url: str) -> str:
        parsed = urlparse(url)
        if parsed.hostname and parsed.hostname.endswith("bing.com"):
            target = parse_qs(parsed.query).get("url", [""])[0]
            if target:
                return unquote(target)
        return url

    @staticmethod
    def _feed_date(value: str) -> datetime | None:
        try:
            return parsedate_to_datetime(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _query_tokens(query: str) -> set[str]:
        stopwords = {"банк", "банка", "банки", "отчет", "отчёт", "статья", "новости"}
        return {
            token
            for token in re.findall(r"[a-zа-яё0-9]+", query.casefold())
            if len(token) >= 4 and token not in stopwords
        }

    @staticmethod
    def _is_relevant(title: str, url: str, tokens: set[str]) -> bool:
        if not tokens:
            return True
        haystack = f"{title} {url}".casefold()
        return any(token in haystack for token in tokens)

    @staticmethod
    def _enrich(article: Article) -> None:
        try:
            validate_public_url(article.url)
            final_url, content = public_get(article.url, timeout=20, max_bytes=5 * 1024 * 1024)
            article.url = canonical_url(final_url)
            page_html = content.decode("utf-8", errors="replace")
            soup = BeautifulSoup(page_html, "html.parser")
            canonical = soup.select_one('link[rel="canonical"][href]')
            if canonical:
                candidate = canonical_url(canonical.get("href", ""))
                validate_public_url(candidate)
                article.url = candidate
            title = soup.select_one('meta[property="og:title"]') or soup.select_one("title")
            if title:
                article.title = (title.get("content") or title.get_text(" ", strip=True))[:300]
            author = soup.select_one('meta[name="author"]') or soup.select_one(
                'meta[property="article:author"]'
            )
            if author:
                article.author = (author.get("content") or "")[:200] or None
            published = soup.select_one('meta[property="article:published_time"]') or soup.select_one(
                'meta[name="date"]'
            )
            if published and published.get("content"):
                article.published_at = datetime.fromisoformat(
                    published["content"].strip().replace("Z", "+00:00")
                )
            article.language = (soup.html.get("lang") if soup.html else None) or None
            extracted = trafilatura.extract(page_html, include_comments=False, include_tables=False)
            if extracted:
                article.excerpt = re.sub(r"\s+", " ", extracted).strip()[:500]
        except Exception:
            return

    def render(self, html_path: str, pdf_path: str | None, png_path: str | None) -> dict:
        with httpx.Client(timeout=180) as client:
            response = client.post(
                f"{self.settings.browser_service_url}/render",
                json={"html_path": html_path, "pdf_path": pdf_path, "png_path": png_path},
            )
            response.raise_for_status()
            return response.json()
