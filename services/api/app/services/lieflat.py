"""Deterministic, offline adapters for the vendored Lieflat template contracts.

The model can select a compatible chart id, but it never supplies executable code.
SVG geometry below follows the corresponding cards in basics-gallery.html.
"""

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from html import escape
from pathlib import Path


LIEFLAT_COMMIT = "eace082a317b696c5570c25826a53a7fa113e984"
SUPPORTED_REPORTS = {
    "financial": ("R04", "templates/reports/report-04.zh.html"),
    "comparison": ("R09", "templates/reports/report-09.zh.html"),
    "brief": ("R11", "templates/reports/report-11.zh.html"),
}
SUPPORTED_CHARTS = {
    "F1",
    "F2",
    "F3",
    "F6",
    "F7",
    "F8",
    "F9",
    "F10",
    "F11",
    "F12",
    "F13",
    "F17",
    "L16",
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
        "financial": "R04 выбран для периодического финансового обзора; R09 слишком KPI-плотный, R11 слишком краткий.",
        "comparison": "R09 выбран для сопоставления KPI; R04 ориентирован на один период, R11 не вмещает сравнение.",
        "brief": "R11 выбран для короткой справки; R04 и R09 требуют больше подтвержденных данных.",
    }
    if root is not None:
        source_path = root / source
        if root.exists() and not source_path.is_file():
            raise RuntimeError(f"Не найден исходный шаблон Lieflat: {source}")
    return TemplateContract(report_id, source, ("R04", "R09", "R11"), reasons.get(kind, reasons["financial"]))


def select_chart(requested: str, facts: list[dict]) -> str:
    requested = requested if requested in SUPPORTED_CHARTS else "F1"
    values = [Decimal(str(item["value"])) for item in facts]
    labels = [str(item.get("label", "")) for item in facts]
    periods_by_metric: dict[str, set[str]] = {}
    for item in facts:
        periods_by_metric.setdefault(str(item.get("metric_code")), set()).add(str(item.get("period_end")))
    if any(value < 0 for value in values):
        return "F9"
    if any(len(periods) >= 2 for periods in periods_by_metric.values()):
        return "F6"
    if any(len(label) > 18 for label in labels):
        return "F5"
    return requested


def _scale(values: list[Decimal], max_units: int = 36) -> Decimal:
    maximum = max([abs(value) for value in values] or [Decimal(1)])
    if maximum <= max_units:
        return Decimal(1)
    raw = maximum / Decimal(max_units)
    magnitude = Decimal(10) ** max(0, raw.adjusted())
    return (raw / magnitude).to_integral_value(rounding=ROUND_CEILING) * magnitude


def rung_chart(facts: list[dict], chart_id: str) -> str:
    """Render the F1/F5 rung grammar as static SVG for offline reports."""

    selected = facts[:8]
    values = [Decimal(str(item["value"])) for item in selected]
    unit = _scale(values)
    horizontal = chart_id == "F5"
    marks: list[str] = []
    if horizontal:
        height = max(230, 42 * len(selected) + 45)
        for index, item in enumerate(selected):
            value = Decimal(str(item["value"]))
            units = int((abs(value) / unit).to_integral_value(rounding=ROUND_CEILING))
            y = 35 + index * 42
            marks.append(f'<text x="132" y="{y + 4}" text-anchor="end">{escape(str(item["label"]))}</text>')
            for step in range(units):
                x = 146 + step * 7
                marks.append(f'<line x1="{x}" y1="{y - 8}" x2="{x}" y2="{y + 8}" class="data"/>')
                if (step + 1) % 5 == 0:
                    marks.append(f'<circle cx="{x}" cy="{y + 13}" r="1" class="grid"/>')
            marks.append(
                f'<text x="{154 + units * 7}" y="{y + 4}" class="value" data-fact-id="{escape(str(item["id"]))}">{escape(str(item["value"]))}</text>'
            )
        viewbox = f"0 0 440 {height}"
    else:
        height = 320
        count = max(1, len(selected))
        spacing = Decimal(340) / Decimal(count)
        for index, item in enumerate(selected):
            value = Decimal(str(item["value"]))
            units = int((abs(value) / unit).to_integral_value(rounding=ROUND_CEILING))
            x = int(50 + spacing * Decimal(index))
            for step in range(units):
                y = 258 - step * 6
                marks.append(f'<line x1="{x - 14}" y1="{y}" x2="{x + 14}" y2="{y}" class="data"/>')
                if (step + 1) % 5 == 0:
                    marks.append(f'<circle cx="{x + 19}" cy="{y}" r="1" class="grid"/>')
            top = 258 - max(0, units - 1) * 6
            marks.append(
                f'<text x="{x}" y="{top - 10}" text-anchor="middle" class="value" data-fact-id="{escape(str(item["id"]))}">{escape(str(item["value"]))}</text>'
            )
            marks.append(f'<text x="{x}" y="280" text-anchor="middle">{escape(str(item["label"]))}</text>')
        marks.append('<line x1="24" y1="264" x2="416" y2="264" class="axis"/>')
        viewbox = "0 0 440 320"
    return (
        f'<svg class="lieflat-chart" data-template="{escape(chart_id)}" viewBox="{viewbox}" role="img" '
        f'aria-label="Проверяемые финансовые показатели"><style>.lieflat-chart text{{font:7px Arial;fill:var(--ink)}}'
        ".lieflat-chart .value{font-size:10px;font-weight:800}.lieflat-chart .data{stroke:var(--ink);stroke-width:1}"
        ".lieflat-chart .grid{fill:var(--faint)}.lieflat-chart .axis{stroke:var(--grid);stroke-width:1}</style>"
        + "".join(marks)
        + f'<text x="220" y="310" text-anchor="middle">ОДНА СТУПЕНЬ = {escape(str(unit))} ЕДИНИЦ</text></svg>'
    )
