import re
from datetime import date, datetime
from html import escape
from urllib.parse import urljoin
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

import httpx
from bs4 import BeautifulSoup


CBR_KEY_RATE_CALENDAR = "https://www.cbr.ru/dkp/cal_mp/"
CBR_KEY_RATE_DECISION = "https://www.cbr.ru/press/keypr/"
CBR_STAT_CALENDAR = "https://www.cbr.ru/statistics/indcalendar/"
CBR_SERVICE = "https://www.cbr.ru/CreditInfoWebServ/CreditOrgInfo.asmx"

RUSSIAN_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


def parse_key_rate_decision_date(content: str) -> date | None:
    text = BeautifulSoup(content, "html.parser").get_text(" ", strip=True)
    months = "|".join(RUSSIAN_MONTHS)
    match = re.search(
        rf"Совет директоров Банка России\s+(\d{{1,2}})\s+({months})\s+(20\d{{2}})\s+года\s+принял решение",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    return date(int(match.group(3)), RUSSIAN_MONTHS[match.group(2).casefold()], int(match.group(1)))

# Offline bootstrap only. Live lookup is always attempted first and is not limited to this list.
BOOTSTRAP_BANKS = [
    {
        "cbr_reg_number": "1481",
        "name": "ПАО Сбербанк",
        "short_name": "Сбер",
        "official_url": "https://www.sberbank.com/ru/investor-relations",
        "aliases": ["сбербанк", "сбер"],
    },
    {
        "cbr_reg_number": "1000",
        "name": "Банк ВТБ (ПАО)",
        "short_name": "ВТБ",
        "official_url": "https://www.vtb.ru/akcionery-i-investory/",
        "aliases": ["втб"],
    },
    {
        "cbr_reg_number": "354",
        "name": "Банк ГПБ (АО)",
        "short_name": "Газпромбанк",
        "official_url": "https://www.gazprombank.ru/about/disclosure/",
        "aliases": ["газпромбанк", "гпб"],
    },
    {
        "cbr_reg_number": "1326",
        "name": "АО АЛЬФА-БАНК",
        "short_name": "Альфа-Банк",
        "official_url": "https://alfabank.ru/about/annual_report/",
        "aliases": ["альфа", "альфа-банк"],
    },
    {
        "cbr_reg_number": "3251",
        "name": "ПАО Банк ПСБ",
        "short_name": "ПСБ",
        "official_url": "https://www.psbank.ru/Bank/Investor",
        "aliases": ["псб", "промсвязьбанк"],
    },
    {
        "cbr_reg_number": "3349",
        "name": "АО Россельхозбанк",
        "short_name": "Россельхозбанк",
        "official_url": "https://www.rshb.ru/about/investors/",
        "aliases": ["рсхб", "россельхозбанк"],
    },
    {
        "cbr_reg_number": "2673",
        "name": "АО ТБанк",
        "short_name": "Т-Банк",
        "official_url": "https://www.tbank.ru/about/financial/",
        "aliases": ["т банк", "т-банк", "тинькофф"],
    },
    {
        "cbr_reg_number": "1978",
        "name": "ПАО МОСКОВСКИЙ КРЕДИТНЫЙ БАНК",
        "short_name": "МКБ",
        "official_url": "https://mkb.ru/investor/reports",
        "aliases": ["мкб", "московский кредитный банк"],
    },
    {
        "cbr_reg_number": "963",
        "name": "ПАО Совкомбанк",
        "short_name": "Совкомбанк",
        "official_url": "https://sovcombank.ru/about/investors",
        "aliases": ["совкомбанк"],
    },
    {
        "cbr_reg_number": "2312",
        "name": "АО Банк ДОМ.РФ",
        "short_name": "Банк ДОМ.РФ",
        "official_url": "https://domrfbank.ru/investors/",
        "aliases": ["дом рф", "банк дом.рф"],
    },
]


class CBRConnector:
    def search_banks(self, query: str) -> list[dict]:
        normalized = query.casefold().replace("ё", "е").strip()
        live = self._soap_search(query)
        merged: dict[str, dict] = {
            item["cbr_reg_number"]: item for item in live if item.get("cbr_reg_number")
        }
        for item in BOOTSTRAP_BANKS:
            haystack = (
                " ".join([item["name"], item.get("short_name", ""), *item.get("aliases", [])])
                .casefold()
                .replace("ё", "е")
            )
            if normalized in haystack or any(normalized == alias for alias in item.get("aliases", [])):
                merged.setdefault(item["cbr_reg_number"], item)
        return list(merged.values())[:20]

    def _soap_search(self, query: str) -> list[dict]:
        try:
            # The ASMX test form is intentionally local-only. Remote clients must
            # use SOAP and the exact NamePart parameter documented by the CBR.
            response_xml = self._soap("SearchByNameXML", {"NamePart": query})
            soup = BeautifulSoup(response_xml, "xml")
            results: list[dict] = []
            for node in soup.find_all(["EnumCredits", "CO", "CreditOrg", "Item", "Org"]):
                values = {
                    child.name.casefold(): child.get_text(" ", strip=True)
                    for child in node.find_all(recursive=False)
                }
                reg = (
                    values.get("cregnr")
                    or values.get("cregnum")
                    or values.get("regnum")
                    or values.get("regnumber")
                    or values.get("reg_num")
                )
                name = values.get("cname") or values.get("name") or values.get("orgname")
                if reg and name:
                    internal_code = values.get("intcode")
                    results.append(
                        {
                            "cbr_reg_number": reg,
                            "name": name,
                            "short_name": values.get("namemini") or name,
                            "official_url": values.get("web")
                            or values.get("site")
                            or self._official_site(internal_code),
                            "aliases": [],
                            "cbr_internal_code": internal_code,
                        }
                    )
            if results:
                return results
            # Some service versions return escaped XML inside a string node.
            text = BeautifulSoup(soup.get_text(), "xml")
            for row in text.find_all("CreditOrg"):
                reg = row.find(["RegNumber", "RegNum"])
                name = row.find(["CName", "Name"])
                if reg and name:
                    results.append(
                        {
                            "cbr_reg_number": reg.get_text(strip=True),
                            "name": name.get_text(strip=True),
                            "short_name": name.get_text(strip=True),
                            "aliases": [],
                        }
                    )
            return results
        except Exception:
            return []

    def _official_site(self, internal_code: str | None) -> str | None:
        if not internal_code:
            return None
        try:
            soup = BeautifulSoup(self._soap("GetSitesXML", {"InternalCode": internal_code}), "xml")
            for node in soup.find_all("URL"):
                url = node.get_text(strip=True)
                if url.startswith(("https://", "http://")) and not any(
                    social in url.casefold() for social in ("vk.com/", "ok.ru/", "t.me/", "telegram.me/")
                ):
                    return url
        except Exception:
            pass
        return None

    def available_form_dates(self, reg_number: str, form: int) -> list[date]:
        if form not in {101, 102}:
            raise ValueError("Поддерживаются только формы 101 и 102")
        method = f"GetDatesForF{form}"
        xml = self._soap(method, {"CredprgNumber": str(int(reg_number))})
        soup = BeautifulSoup(xml, "xml")
        result: list[date] = []
        for node in soup.find_all("dateTime"):
            try:
                result.append(datetime.fromisoformat(node.get_text(strip=True).replace("Z", "+00:00")).date())
            except ValueError:
                continue
        return sorted(set(result))

    def fetch_form(self, reg_number: str, form: int, date_from: date, date_to: date) -> bytes:
        if form == 101:
            dates = [
                item
                for item in self.available_form_dates(reg_number, 101)
                if date_from <= item <= date_to
            ]
            if not dates:
                raise ValueError("У ЦБ нет формы 101 за выбранный период")
            if len(dates) > 24:
                raise ValueError("За один запрос можно получить не более 24 периодов формы 101")
            combined = ElementTree.Element(
                "CBRForms", {"form": "101", "reg_number": str(int(reg_number))}
            )
            for report_date in dates:
                response = self._soap(
                    "Data101FNewXML",
                    {
                        "CredorgNumber": str(int(reg_number)),
                        "Dt": f"{report_date.isoformat()}T00:00:00",
                    },
                )
                envelope = ElementTree.fromstring(response)
                result = next(
                    (
                        node
                        for node in envelope.iter()
                        if node.tag.rsplit("}", 1)[-1] == "Data101FNewXMLResult"
                    ),
                    None,
                )
                if result is not None:
                    for child in result:
                        combined.append(child)
            return ElementTree.tostring(combined, encoding="utf-8", xml_declaration=True)
        elif form == 102:
            method = "Data102FXML"
            params = {"CredorgNumber": str(int(reg_number)), "dt": f"{date_to.isoformat()}T00:00:00"}
        else:
            raise ValueError("Поддерживаются только формы 101 и 102")
        return self._soap(method, params).encode("utf-8")

    @staticmethod
    def _soap(method: str, params: dict[str, str]) -> str:
        fields = "".join(f"<{key}>{escape(value)}</{key}>" for key, value in params.items())
        envelope = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<soap:Envelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            f'<soap:Body><{method} xmlns="http://web.cbr.ru/">{fields}</{method}></soap:Body>'
            "</soap:Envelope>"
        )
        with httpx.Client(transport=httpx.HTTPTransport(retries=2), timeout=90) as client:
            response = client.post(
                CBR_SERVICE,
                content=envelope.encode("utf-8"),
                headers={
                    "Content-Type": "text/xml; charset=utf-8",
                    "SOAPAction": f'"http://web.cbr.ru/{method}"',
                },
            )
            response.raise_for_status()
            return response.text

    def sync_editorial_calendar(self) -> list[dict]:
        events = self._key_rate_events() + self._stat_events()
        published_on = self.latest_key_rate_decision()
        if published_on:
            for item in events:
                if item["event_type"] == "key_rate_meeting" and item["starts_at"].date() == published_on:
                    item["status"] = "published"
                    item["source_url"] = CBR_KEY_RATE_DECISION
        return events

    def latest_key_rate_decision(self) -> date | None:
        try:
            response = httpx.get(CBR_KEY_RATE_DECISION, timeout=30, follow_redirects=True)
            response.raise_for_status()
            return parse_key_rate_decision_date(response.text)
        except Exception:
            return None

    def _key_rate_events(self) -> list[dict]:
        try:
            html = httpx.get(CBR_KEY_RATE_CALENDAR, timeout=30, follow_redirects=True).text
        except Exception:
            return []
        text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
        months = RUSSIAN_MONTHS
        pattern = re.compile(r"(\d{1,2})\s+(" + "|".join(months) + r")\s+(20\d{2})\s+года")
        events: list[dict] = []
        for match in pattern.finditer(text):
            context = text[match.end() : match.end() + 220]
            if "Заседание Совета директоров" not in context and "Резюме обсуждения" not in context:
                continue
            event_type = (
                "key_rate_meeting" if "Заседание Совета директоров" in context else "key_rate_summary"
            )
            hour, minute = (13, 30) if event_type == "key_rate_meeting" else (10, 0)
            starts = datetime(
                int(match.group(3)),
                months[match.group(2)],
                int(match.group(1)),
                hour,
                minute,
                tzinfo=ZoneInfo("Europe/Moscow"),
            )
            title = (
                "Решение Банка России по ключевой ставке"
                if event_type == "key_rate_meeting"
                else "Резюме обсуждения ключевой ставки"
            )
            events.append(
                {
                    "external_key": f"cbr:{event_type}:{starts.date()}",
                    "title": title,
                    "event_type": event_type,
                    "starts_at": starts,
                    "status": "confirmed",
                    "confidence": "high",
                    "source_url": CBR_KEY_RATE_CALENDAR,
                }
            )
        return list({item["external_key"]: item for item in events}.values())

    def _stat_events(self) -> list[dict]:
        try:
            html = httpx.get(CBR_STAT_CALENDAR, timeout=30, follow_redirects=True).text
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return []
        events: list[dict] = []
        for row in soup.select("table tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
            if len(cells) < 2:
                continue
            date_match = re.search(r"(\d{2})\.(\d{2})\.(20\d{2})", cells[0])
            if not date_match:
                continue
            title = cells[-1][:600]
            editorial = any(
                key in title.casefold()
                for key in ("банков", "финансовой стабильности", "денежно-кредит", "годовой отчет")
            )
            if not editorial:
                continue
            hour_match = re.search(r"(\d{1,2}):(\d{2})", " ".join(cells[:-1]))
            hour, minute = (int(hour_match.group(1)), int(hour_match.group(2))) if hour_match else (10, 0)
            starts = datetime(
                int(date_match.group(3)),
                int(date_match.group(2)),
                int(date_match.group(1)),
                hour,
                minute,
                tzinfo=ZoneInfo("Europe/Moscow"),
            )
            key = re.sub(r"\W+", "-", title.casefold())[:120]
            events.append(
                {
                    "external_key": f"cbr:stat:{starts.date()}:{key}",
                    "title": title,
                    "event_type": "cbr_publication",
                    "starts_at": starts,
                    "status": "confirmed",
                    "confidence": "high",
                    "source_url": CBR_STAT_CALENDAR,
                }
            )
        return events


def discover_document_links(
    page_url: str, html: str, kind: str | None = None, period: str | None = None
) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict] = []
    tokens = [value.casefold() for value in (kind, period) if value]
    for link in soup.select("a[href]"):
        href = urljoin(page_url, link.get("href", ""))
        label = link.get_text(" ", strip=True) or href.rsplit("/", 1)[-1]
        combined = f"{label} {href}".casefold()
        if not re.search(r"\.(pdf|xlsx?|csv|zip|dbf)(?:$|\?)", href, re.I):
            continue
        if tokens and not all(token in combined for token in tokens):
            continue
        standard = (
            "ifrs" if "мсфо" in combined or "ifrs" in combined else "ras" if "рсбу" in combined else None
        )
        results.append({"title": label[:600], "url": href, "reporting_standard": standard})
    return results
