import hashlib
import re
from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup


MINFIN_SECTIONS = {
    "public_debt": "https://minfin.gov.ru/ru/perfomance/public_debt/",
    "budget": "https://minfin.gov.ru/ru/statistics/fedbud/",
    "national_wealth_fund": "https://minfin.gov.ru/ru/perfomance/nationalwealthfund/",
}


class MinfinConnector:
    """Best-effort public monitor; unavailable sections never block the rest of a run."""

    keywords = ("офз", "аукцион", "долг", "бюджет", "фонд национального благосостояния", "фнб")

    def discover_publications(self) -> list[dict]:
        events: list[dict] = []
        for section, url in MINFIN_SECTIONS.items():
            try:
                response = httpx.get(url, timeout=30, follow_redirects=True)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
            except Exception:
                continue
            for link in soup.select("a[href]"):
                title = link.get_text(" ", strip=True)
                if not title or not any(word in title.casefold() for word in self.keywords):
                    continue
                container_text = link.parent.get_text(" ", strip=True) if link.parent else title
                match = re.search(r"(\d{2})[./](\d{2})[./](20\d{2})", container_text)
                if not match:
                    continue
                starts = datetime(
                    int(match.group(3)),
                    int(match.group(2)),
                    int(match.group(1)),
                    10,
                    0,
                    tzinfo=ZoneInfo("Europe/Moscow"),
                )
                href = urljoin(url, link.get("href", ""))
                digest = hashlib.sha1(href.encode(), usedforsecurity=False).hexdigest()[:16]
                events.append(
                    {
                        "external_key": f"minfin:{section}:{digest}",
                        "title": title[:600],
                        "event_type": f"minfin_{section}",
                        "starts_at": starts,
                        "status": "published",
                        "confidence": "high",
                        "source_url": href,
                    }
                )
        return list({item["external_key"]: item for item in events}.values())
