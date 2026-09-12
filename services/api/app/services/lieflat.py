"""Deterministic offline adapters for the vendored Lieflat contracts.

The model selects a compatible chart id but never supplies executable code.
"""

from dataclasses import dataclass
from decimal import Decimal
from html import escape
from pathlib import Path


LIEFLAT_COMMIT = "eace082a317b696c5570c25826a53a7fa113e984"
SUPPORTED_REPORTS = {
    "financial": ("R04", "templates/reports/report-04.zh.html"),
    "comparison": ("R09", "templates/reports/report-09.zh.html"),
    "brief": ("R11", "templates/reports/report-11.zh.html"),
}
SUPPORTED_CHARTS = {
    "F1", "F2", "F3", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "F13", "F17", "L16"
}
PERCENT_METRICS = {
    "capital_adequacy",
    "capital_adequacy_ratio",
    "npl",
    "npl_ratio",
    "roa",
    "roe",
}


@dataclass(frozen=True)
class TemplateContract:
    report_id: str
    source_file: str
    candidates: tuple[str, str, str]
    selection_reason: str


def report_contract(kind: str, root: Path | None = None) -> TemplateContract:
    report_id, source = SUPPORTED_REPORTS.get(kind, SUPPORTED_REPORTS["financial"])
    reasons = {
        "financial": "R04 выбран для периодического финансового обзора; R09 предназначен для KPI-сравнения, R11 — для краткой справки.",
        "comparison": "R09 выбран для сопоставления KPI; R04 ориентирован на один период, R11 не вмещает подробное сравнение.",
        "brief": "R11 выбран для короткой корреспондентской справки; R04 и R09 требуют больше подтвержденных данных.",
    }
    if root is not None:
        source_path = root / source
        if root.exists() and not source_path.is_file():
            raise RuntimeError(f"Не найден исходный шаблон Lieflat: {source}")
    return TemplateContract(
        report_id,
        source,
        ("R04", "R09", "R11"),
        reasons.get(kind, reasons["financial"]),
    )


def select_chart(requested: str, facts: list[dict]) -> str:
    requested = requested if requested in SUPPORTED_CHARTS else "F1"
    values = [Decimal(str(item["value"])) for item in facts]
    periods_by_metric: dict[str, set[str]] = {}
    for item in sorted(facts, key=lambda fact: str(fact.get("period_end") or ""), reverse=True):
        periods_by_metric.setdefault(str(item.get("metric_code")), set()).add(str(item.get("period_end")))
    if any(value < 0 for value in values):
        return "F9"
    if any(len(periods) >= 2 for periods in periods_by_metric.values()):
        return "F6"
    return requested


def format_number(value: Decimal) -> str:
    """Format a Decimal for reading while keeping exact values in data exports."""
    if value == value.to_integral_value():
        rendered = f"{value:,.0f}"
    else:
        decimals = min(2, max(1, -value.as_tuple().exponent))
        rendered = f"{value:,.{decimals}f}".rstrip("0").rstrip(".")
    return rendered.replace(",", "\u202f").replace(".", ",")


def format_fact_value(item: dict) -> str:
    value = Decimal(str(item["value"]))
    metric = str(item.get("metric_code") or "").lower()
    currency = str(item.get("currency") or "").upper()
    scale = int(item.get("unit_scale") or 1)
    if metric in PERCENT_METRICS or currency in {"%", "PERCENT"}:
        return f"{format_number(value)}%"
    currency_label = {"RUB": "₽", "RUR": "₽", "USD": "$", "EUR": "€"}.get(currency, currency)
    absolute_base = abs(value * scale)
    display_scale = scale
    if currency_label and absolute_base >= Decimal("1000000000000"):
        display_scale = 1_000_000_000_000
    elif currency_label and absolute_base >= Decimal("1000000000"):
        display_scale = 1_000_000_000
    elif currency_label and absolute_base >= Decimal("1000000"):
        display_scale = 1_000_000
    elif currency_label and absolute_base >= Decimal("1000"):
        display_scale = 1_000
    display_value = value * Decimal(scale) / Decimal(display_scale)
    scale_label = {
        1_000: "тыс.",
        1_000_000: "млн",
        1_000_000_000: "млрд",
        1_000_000_000_000: "трлн",
    }.get(display_scale, "")
    suffix = " ".join(part for part in (scale_label, currency_label) if part)
    return f"{format_number(display_value)}{f' {suffix}' if suffix else ''}"


def rung_chart(facts: list[dict], chart_id: str) -> str:
    """Render a restrained Lieflat-compatible horizontal comparison chart."""
    selected: list[dict] = []
    seen_metrics: set[str] = set()
    for item in sorted(facts, key=lambda fact: str(fact.get("period_end") or ""), reverse=True):
        metric = str(item.get("metric_code") or item.get("label"))
        if metric in seen_metrics:
            continue
        selected.append(item)
        seen_metrics.add(metric)
        if len(selected) == 8:
            break
    def magnitude(item: dict) -> Decimal:
        value = abs(Decimal(str(item["value"])))
        metric = str(item.get("metric_code") or "").lower()
        if metric in PERCENT_METRICS or str(item.get("currency") or "").upper() in {"%", "PERCENT"}:
            return value
        return value * Decimal(int(item.get("unit_scale") or 1))

    values = [magnitude(item) for item in selected]
    maximum = max(values or [Decimal(1)]) or Decimal(1)
    height = max(140, len(selected) * 62 + 28)
    marks: list[str] = []
    for index, item in enumerate(selected):
        raw_value = Decimal(str(item["value"]))
        item_magnitude = magnitude(item)
        ratio = float(item_magnitude / maximum) if item_magnitude else 0
        bar_width = max(8, int(390 * ratio**0.5)) if item_magnitude else 0
        y = 22 + index * 62
        label = str(item.get("label") or item.get("metric_code") or "Показатель")
        short_label = label if len(label) <= 38 else f"{label[:37]}…"
        period = str(item.get("period_end") or "")
        marks.append(
            f'<text x="0" y="{y}" class="label"><title>{escape(label)}</title>{escape(short_label)}</text>'
        )
        marks.append(
            f'<text x="720" y="{y}" text-anchor="end" class="value" '
            f'data-fact-id="{escape(str(item["id"]))}">{escape(format_fact_value(item))}</text>'
        )
        marks.append(f'<rect x="0" y="{y + 13}" width="390" height="10" rx="5" class="track"/>')
        negative = " negative" if raw_value < 0 else ""
        marks.append(
            f'<rect x="0" y="{y + 13}" width="{bar_width}" height="10" rx="5" class="bar{negative}"/>'
        )
        if period:
            marks.append(
                f'<text x="720" y="{y + 24}" text-anchor="end" class="period">{escape(period)}</text>'
            )
    viewbox = f"0 0 720 {height}"
    return (
        f'<svg class="lieflat-chart" data-template="{escape(chart_id)}" viewBox="{viewbox}" role="img" '
        'aria-label="Проверяемые финансовые показатели"><style>'
        ".lieflat-chart text{font:13px ui-sans-serif,system-ui,sans-serif;fill:var(--ink)}"
        ".lieflat-chart .label{font-weight:650}.lieflat-chart .value{font-size:14px;font-weight:800}"
        ".lieflat-chart .period{font-size:9px;fill:var(--muted)}.lieflat-chart .track{fill:var(--track)}"
        ".lieflat-chart .bar{fill:var(--accent)}.lieflat-chart .bar.negative{fill:var(--danger)}</style>"
        + "".join(marks)
        + "</svg>"
    )
