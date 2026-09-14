import json
import re
from urllib.parse import urlencode, urljoin

from .network import public_get_sequence


GAZPROMBANK_ORIGIN = "https://www.gazprombank.ru"
GAZPROMBANK_DOCUMENTS = f"{GAZPROMBANK_ORIGIN}/documents-and-tariffs/"


def _requested_standard(kind: str | None) -> tuple[str, str]:
    value = (kind or "").casefold()
    if any(token in value for token in ("рсбу", "ras")):
        return "РСБУ отчетность", "ras"
    return "МСФО отчетность", "ifrs"


def _section_id(html: str, section_label: str, year: int | None) -> tuple[str, int] | None:
    marker = f'"label":"{section_label}"'
    start = html.find(marker)
    if start < 0:
        return None
    children_start = html.find('"children":[', start)
    if children_start < 0:
        return None
    children_end = html.find("]}", children_start)
    if children_end < 0:
        return None
    choices = [
        (int(match.group("year")), match.group("section"))
        for match in re.finditer(
            r'\{"label":"(?P<year>20\d{2})","value":(?P<section>\d+),"children":null\}',
            html[children_start:children_end],
        )
    ]
    if not choices:
        return None
    if year is not None:
        return next(((section, item_year) for item_year, section in choices if item_year == year), None)
    item_year, section = max(choices)
    return section, item_year


def _flatten_documents(items: list[dict]) -> list[dict]:
    flattened: list[dict] = []
    for item in items:
        flattened.append(item)
        flattened.extend(_flatten_documents(item.get("attachments") or []))
    return flattened


def discover_gazprombank_documents(
    kind: str | None = None, period: str | None = None
) -> list[dict]:
    """Read Gazprombank's public document API through its required cookie session."""
    section_label, standard = _requested_standard(kind)
    year_match = re.search(r"20\d{2}", period or "")
    requested_year = int(year_match.group(0)) if year_match else None
    listing_url = f"{GAZPROMBANK_DOCUMENTS}?{urlencode({'sectionId': 325})}"
    (_, bootstrap) = public_get_sequence([listing_url], timeout=20, max_bytes=10 * 1024 * 1024)[0]
    selected = _section_id(bootstrap.decode("utf-8", errors="replace"), section_label, requested_year)
    if not selected:
        return []
    section_id, selected_year = selected
    section_root = "341" if standard == "ifrs" else "82471"
    portal_url = (
        f"{GAZPROMBANK_DOCUMENTS}?sectionId=325&subSectionId={section_root}-{section_id}"
    )
    api_url = f"{GAZPROMBANK_ORIGIN}/rest/document/list/?{urlencode({
        'sectionId': section_id,
        'page': 1,
        # The public endpoint validates this against an A/B-dependent range;
        # five is accepted by every currently served frontend variant.
        'pageSize': 5,
        'cityId': 617,
        'ab_segment': 'SEGMENT_ERROR',
    })}"
    # The endpoint requires cookies set by the preceding HTML response, so the
    # two requests intentionally share one session.
    responses = public_get_sequence(
        [portal_url, api_url], timeout=30, max_bytes=10 * 1024 * 1024
    )
    payload = json.loads(responses[-1][1])
    results: list[dict] = []
    for item in _flatten_documents(payload.get("data") or []):
        source = item.get("src")
        title = (item.get("name") or "").strip()
        if not source or not title:
            continue
        url = urljoin(GAZPROMBANK_ORIGIN, source)
        results.append(
            {
                "title": title[:600],
                "url": url,
                "reporting_standard": standard,
                "source_tier": "official_bank",
                "published_at": item.get("createdAt"),
                "reporting_year": selected_year,
                "portal_url": portal_url,
            }
        )
    return results
