from datetime import date
from pathlib import Path
from types import SimpleNamespace

from app.services.lieflat import (
    LIEFLAT_COMMIT,
    chart_contract,
    comparison_pairs,
    format_fact_value,
    report_contract,
    rung_chart,
)
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
    assert 'data-fact-id="fact-new"' in rendered
    assert "125 ₽" in rendered
    assert 'class="bar"' in rendered


def test_two_period_facts_use_real_f6_paired_rungs_contract():
    contract = chart_contract(facts())
    rendered = rung_chart(facts(), contract.chart_id)
    assert contract.chart_id == "F6"
    assert contract.candidates == ("F6", "F12", "F1")
    assert 'data-template="F6"' in rendered
    assert 'data-gallery="templates/basics-gallery.html"' in rendered
    assert 'class="bar rung previous"' in rendered
    assert 'class="bar rung current"' in rendered
    assert "2025" in rendered and "2026" in rendered
    assert "ИЗМЕНЕНИЕ +25%" in rendered
    assert comparison_pairs(facts()) == [(facts()[0], facts()[1])]


def test_single_period_is_not_presented_as_dynamics():
    contract = chart_contract([facts()[1]])
    assert contract.chart_id == "F5"
    assert comparison_pairs([facts()[1]]) == []


def test_ratio_is_formatted_as_percent_even_if_source_currency_is_rub():
    assert format_fact_value(
        {"metric_code": "capital_adequacy_ratio", "value": "14.70000000", "currency": "RUB"}
    ) == "14,7%"


def test_financial_value_is_presented_in_readable_scale():
    assert format_fact_value(
        {
            "value": "4873717",
            "unit_scale": 1_000_000,
            "currency": "RUB",
            "metric_code": "assets",
        }
    ) == "4,87 трлн ₽"
    assert format_fact_value(
        {
            "value": "22.6",
            "unit_scale": 1_000_000_000,
            "currency": "RUB",
            "metric_code": "net_profit",
        }
    ) == "22,6 млрд ₽"


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
    assert '<details class="sources">' in rendered
    assert "125 ₽" in rendered
    assert 'data-template-source="templates/reports/report-04.zh.html"' in rendered
    assert "LIEFLAT 报告模板 04" in rendered
    assert "REAL TEMPLATE FROM BASICS-GALLERY.HTML" in rendered
    assert 'class="comparison-table"' in rendered
    assert "Предыдущий период" in rendered
    assert "+25%" in rendered


def test_comparison_and_brief_use_vendored_report_skeletons():
    service = ReportService.__new__(ReportService)
    service.models = SimpleNamespace(settings=SimpleNamespace(lieflat_dir=Path("/opt/lieflat-charts")))
    narrative = {
        "summary": "Прибыль изменилась.",
        "highlights": [{"text": "Рост подтвержден.", "fact_ids": ["fact-old", "fact-new"]}],
        "risks": [],
        "chart": {"template": "F6", "metric_codes": ["net_profit"]},
    }
    comparison = service._html(
        SimpleNamespace(title="Сравнение", report_kind="comparison"), narrative, facts()
    )
    brief = service._html(SimpleNamespace(title="Справка", report_kind="brief"), narrative, facts())
    assert 'data-lieflat-report="R09"' in comparison
    assert 'data-template-source="templates/reports/report-09.zh.html"' in comparison
    assert "LIEFLAT 报告模板 09" in comparison
    assert 'data-lieflat-report="R11"' in brief
    assert 'data-template-source="templates/reports/report-11.zh.html"' in brief
    assert "LIEFLAT 报告模板 11" in brief
    assert "<script src=" not in comparison + brief


def test_decimal_calculations_feed_xlsx():
    rows = ReportService._calculations(facts())
    assert rows[0]["growth_percent"] == "25.00"
    assert rows[0]["fact_ids"] == ["fact-old", "fact-new"]
