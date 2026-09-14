from datetime import date

from app.services.cbr import CBRConnector, discover_document_links, parse_key_rate_decision_date


def test_offline_alias_resolution(monkeypatch):
    monkeypatch.setattr(CBRConnector, "_soap_search", lambda *_: [])
    result = CBRConnector().search_banks("Сбер")
    assert result[0]["cbr_reg_number"] == "1481"


def test_live_search_parses_cbr_enum_and_official_site(monkeypatch):
    search = """<Envelope><Body><SearchByNameXMLResult><CreditOrg><EnumCredits>
    <IntCode>42</IntCode><OrgName>АО Тест Банк</OrgName><cregnr>9999</cregnr>
    </EnumCredits></CreditOrg></SearchByNameXMLResult></Body></Envelope>"""
    sites = """<Envelope><GetSitesXMLResult><CredorgSites>
    <SC><URL>https://test-bank.example</URL></SC>
    </CredorgSites></GetSitesXMLResult></Envelope>"""

    def soap(_method, _params):
        return sites if _method == "GetSitesXML" else search

    monkeypatch.setattr(CBRConnector, "_soap", staticmethod(soap))
    result = CBRConnector().search_banks("Тест Банк")
    assert result[0]["cbr_reg_number"] == "9999"
    assert result[0]["official_url"] == "https://test-bank.example"


def test_curated_disclosure_url_replaces_non_disclosure_cbr_site(monkeypatch):
    monkeypatch.setattr(
        CBRConnector,
        "_soap_search",
        lambda *_: [
            {
                "cbr_reg_number": "1978",
                "name": "ПАО МОСКОВСКИЙ КРЕДИТНЫЙ БАНК",
                "short_name": "МКБ",
                "official_url": "https://dzen.ru/mkb",
                "aliases": [],
            },
            {
                "cbr_reg_number": "9998",
                "name": "МКБ «Дон-Тексбанк» ООО",
                "short_name": "МКБ «Дон-Тексбанк»",
                "official_url": "https://example.org",
                "aliases": [],
            },
        ],
    )
    result = CBRConnector().search_banks("МКБ")
    assert len(result) == 1
    assert result[0]["official_url"] == "https://ir.mkb.ru/investor-relations/reports/ifrs"


def test_document_discovery_only_returns_supported_files():
    html = '<a href="/ifrs-2026.pdf">МСФО 2026</a><a href="/news">Новость</a>'
    result = discover_document_links("https://bank.example/investors/", html, "мсфо", "2026")
    assert result == [
        {"title": "МСФО 2026", "url": "https://bank.example/ifrs-2026.pdf", "reporting_standard": "ifrs"}
    ]


def test_document_discovery_supports_extensionless_disclosure_pdf_routes():
    html = '<a href="/file/59c2d59e-b9ff-438e-9137-17bae2fb3975">Обобщенная отчетность по МСФО за 12 месяцев</a>'
    result = discover_document_links(
        "https://ir.mkb.ru/investor-relations/reports/ifrs/2025", html, "МСФО", "2025 год"
    )
    assert result == [
        {
            "title": "Обобщенная отчетность по МСФО за 12 месяцев",
            "url": "https://ir.mkb.ru/file/59c2d59e-b9ff-438e-9137-17bae2fb3975",
            "reporting_standard": "ifrs",
        }
    ]


def test_document_discovery_supports_storage_attachment_and_document_routes():
    html = """
    <a href="/api/v1/storage/4154c821-a3bb-44c1-b00a-c96318d05f43/attachment">
      Отчётность по Международным стандартам (МСФО) за 2025 год
    </a>
    <a href="https://sovcombank.ru/document/16976">Результаты МСФО за 2025 год</a>
    """
    result = discover_document_links("https://www.rshb.ru/reports", html, "МСФО", "2025")
    assert len(result) == 2
    assert result[0]["reporting_standard"] == "ifrs"


def test_document_discovery_parses_browser_snapshot_and_compact_year():
    snapshot = """
    - link [ref=e1, url=https://www.vtb.ru/media/ifrs_1225_rus.pdf]
    - link [ref=e2, url=https://www.vtb.ru/media/presentation_ifrs_1225_rus.pdf]
    """
    result = discover_document_links(
        "https://www.vtb.ru/ir/statements/results/", snapshot, "МСФО", "2025"
    )
    assert len(result) == 2
    assert result[0]["url"].endswith("ifrs_1225_rus.pdf")


def test_full_statement_is_ranked_above_auditor_report_and_presentation():
    html = """
    <a href="/audit_ifrs_2025.pdf">Аудиторское заключение по МСФО за 2025 год</a>
    <a href="/presentation_ifrs_2025.pdf">Презентация по МСФО за 2025 год</a>
    <a href="/statement_ifrs_2025.pdf">Консолидированная финансовая отчетность по МСФО за 2025 год</a>
    """
    result = discover_document_links("https://bank.example/ifrs", html, "МСФО", "2025")
    assert result[0]["url"].endswith("statement_ifrs_2025.pdf")


def test_annual_statement_is_ranked_above_later_published_half_year_report():
    html = """
    <a href="/published-2026/ifrs-half-year-2025.pdf">
      IFRS financial statements for half-year 2025
    </a>
    <a href="/ifrs-annual-2025.pdf">
      Consolidated IFRS financial statements for 2025 year
    </a>
    """
    result = discover_document_links("https://bank.example/ifrs", html, "IFRS", "2025")
    assert result[0]["url"].endswith("ifrs-annual-2025.pdf")


def test_explicit_reporting_year_beats_compact_publication_date_in_url():
    html = """
    <a href="/IFRS_Report_010126_RUS.pdf">IFRS statements for 2025</a>
    <a href="/IFRS_Report_010125_RUS.pdf">IFRS statements for 2024</a>
    """
    result = discover_document_links("https://bank.example/ifrs", html, "IFRS", "2025")
    assert [item["url"] for item in result] == [
        "https://bank.example/IFRS_Report_010126_RUS.pdf"
    ]


def test_document_discovery_uses_nearby_title_for_icon_only_pdf_link():
    html = """
    <article>
      <time>11 августа 2026</time>
      <div>
        <span>Финансовые результаты по МСФО за II квартал 2026 года</span>
        <a href="https://cdn.bank.example/result.pdf" aria-label="pdf"></a>
      </div>
    </article>
    """
    result = discover_document_links(
        "https://bank.example/press-releases/", html, "МСФО", "2026"
    )
    assert result
    assert result[-1]["title"] == "Финансовые результаты по МСФО за II квартал 2026 года"
    assert result[-1]["reporting_standard"] == "ifrs"


def test_published_key_rate_decision_date_is_extracted():
    html = """<main>Совет директоров Банка России 11 сентября 2026 года
    принял решение сохранить ключевую ставку.</main>"""
    assert parse_key_rate_decision_date(html) == date(2026, 9, 11)


def test_form_dates_and_form_validation(monkeypatch):
    monkeypatch.setattr(
        CBRConnector,
        "_soap",
        staticmethod(lambda *_: "<root><dateTime>2026-01-01T00:00:00</dateTime></root>"),
    )
    assert CBRConnector().available_form_dates("1481", 101) == [date(2026, 1, 1)]
    try:
        CBRConnector().fetch_form("1481", 999, date(2026, 1, 1), date(2026, 2, 1))
    except ValueError as exc:
        assert "101 и 102" in str(exc)
    else:
        raise AssertionError("Unsupported CBR form must fail")


def test_form_101_fetches_each_available_period(monkeypatch):
    connector = CBRConnector()
    monkeypatch.setattr(
        connector,
        "available_form_dates",
        lambda *_: [date(2026, 1, 1), date(2026, 2, 1)],
    )
    calls = []

    def soap(method, params):
        calls.append((method, params))
        return (
            "<Envelope><Data101FNewXMLResult><F101FNew>"
            f"<F101><numsc>101</numsc><vitg>{len(calls)}</vitg></F101>"
            "</F101FNew></Data101FNewXMLResult></Envelope>"
        )

    monkeypatch.setattr(connector, "_soap", soap)
    payload = connector.fetch_form("1927", 101, date(2026, 1, 1), date(2026, 2, 1))
    assert payload.count(b"F101FNew") == 4
    assert [call[0] for call in calls] == ["Data101FNewXML", "Data101FNewXML"]
