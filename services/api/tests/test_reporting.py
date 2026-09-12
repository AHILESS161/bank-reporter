from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.services.lieflat import LIEFLAT_COMMIT, report_contract, rung_chart
from app.services.reporting import ReportService


def facts():
    return [
        {
            "id": "fact-old",
            "metric_code": "net_profit",
            "label": "Чистая прибыль",
            "value": "100.00",
            "currency": "RUB",
            "unit_scale": 1,
            "period_end": date(2025, 12, 31),
            "confidence": "high",
            "document": "МСФО 2025",
            "source_url": "https://bank.example/ifrs-2025.pdf",
            "page": 7,
            "sheet": None,
            "cell_range": None,
        },
        {
            "id": "fact-new",
            "metric_code": "net_profit",
            "label": "Чистая прибыль",
            "value": "125.00",
            "currency": "RUB",
            "unit_scale": 1,
            "period_end": date(2026, 12, 31),
            "confidence": "high",
            "document": "МСФО 2026",
            "source_url": "https://bank.example/ifrs-2026.pdf",
            "page": 8,
            "sheet": None,
            "cell_range": None,
        },
    ]


def test_lieflat_contract_points_to_vendored_source():
    container_root = Path("/opt/lieflat-charts")
    root = (
        container_root
        if container_root.is_dir()
        else Path(__file__).resolve().parents[3] / "third_party" / "lieflat-charts"
    )
    contract = report_contract("financial", root)
    assert contract.report_id == "R04"
    assert (root / contract.source_file).is_file()


def test_rung_chart_uses_fact_provenance_and_honest_unit():
    rendered = rung_chart(facts(), "F1")
    assert 'data-template="F1"' in rendered
    assert 'data-fact-id="fact-old"' in rendered
    assert "ОДНА СТУПЕНЬ" in rendered


def test_report_html_is_offline_and_has_no_demo_data():
    service = ReportService.__new__(ReportService)
    service.models = SimpleNamespace(settings=SimpleNamespace(lieflat_dir=Path("missing")))
    report = SimpleNamespace(title="Проверяемый отчет", report_kind="financial")
    narrative = {
        "summary": "Прибыль изменилась.",
        "highlights": [{"text": "Рост подтвержден.", "fact_ids": ["fact-old", "fact-new"]}],
        "risks": [],
        "chart": {"template": "F6", "metric_codes": ["net_profit"]},
    }
    rendered = service._html(report, narrative, facts())
    assert LIEFLAT_COMMIT in rendered
    assert "<script src=" not in rendered
    assert "fonts.googleapis.com" not in rendered
    assert "1,502" not in rendered
    assert "yoursite.com" not in rendered
    assert "fact-old" in rendered and "fact-new" in rendered
    assert "Не является инвестиционной рекомендацией" in rendered


def test_decimal_calculations_feed_xlsx():
    rows = ReportService._calculations(facts())
    assert rows[0]["growth_percent"] == "25.00"
    assert rows[0]["fact_ids"] == ["fact-old", "fact-new"]
