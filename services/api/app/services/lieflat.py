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
    "F1", "F2", "F3", "F5", "F6", "F7", "F8", "F9", "F10", "F11", "F12", "F13", "F17", "L16"
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


@dataclass(frozen=True)
class ChartContract:
    chart_id: str
    source_file: str
    source_title: str
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


def template_styles(contract: TemplateContract, root: Path | None) -> str:
    """Read the real vendored report stylesheet; never fetch template assets at runtime."""
    candidates = []
    if root is not None:
        candidates.append(root / contract.source_file)
    candidates.append(Path("/opt/lieflat-charts") / contract.source_file)
    candidates.extend(
        parent / "third_party" / "lieflat-charts" / contract.source_file
        for parent in Path(__file__).resolve().parents
    )
    source_path = next((path for path in candidates if path.is_file()), None)
    if source_path is None:
        return ""
    source = source_path.read_text(encoding="utf-8")
    start = source.find("<style>")
    end = source.find("</style>", start)
    return source[start + len("<style>") : end] if start >= 0 and end > start else ""


def chart_contract(facts: list[dict]) -> ChartContract:
    if comparison_pairs(facts):
        return ChartContract(
            "F6",
            "templates/basics-gallery.html",
            "This year against last, plan by plan",
            ("F6", "F12", "F1"),
            "F6 сохраняет две серии по каждому показателю; F12 требует единой счетной единицы между точками, F1 не показывает второй период.",
        )
    return ChartContract(
        "F5",
        "templates/basics-gallery.html",
        "Six teams, shipped and counted",
        ("F5", "F1", "L2"),
        "F5 выбран для длинных русских названий; вертикальный F1 и L2 не вмещают подписи без сокращений.",
    )


def select_chart(requested: str, facts: list[dict]) -> str:
    contract = chart_contract(facts)
    if contract.chart_id in SUPPORTED_CHARTS:
        return contract.chart_id
    return requested if requested in SUPPORTED_CHARTS else "F1"


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


def comparison_pairs(facts: list[dict], limit: int = 6) -> list[tuple[dict, dict]]:
    """Return honest previous/current pairs, preferring two periods from one document."""
    grouped: dict[str, list[dict]] = {}
    for item in facts:
        if item.get("period_end"):
            grouped.setdefault(str(item.get("metric_code") or item.get("label")), []).append(item)

    def compatible(left: dict, right: dict) -> bool:
        left_currency = str(left.get("currency") or "").upper().replace("RUR", "RUB")
        right_currency = str(right.get("currency") or "").upper().replace("RUR", "RUB")
        return left_currency == right_currency

    def choose(items: list[dict]) -> tuple[dict, dict] | None:
        by_period: dict[str, dict] = {}
        confidence = {"high": 3, "medium": 2, "low": 1}
        for item in sorted(
            items,
            key=lambda fact: (
                str(fact.get("period_end") or ""),
                confidence.get(str(fact.get("confidence") or "").lower(), 0),
                bool(fact.get("page") or fact.get("sheet") or fact.get("cell_range")),
            ),
            reverse=True,
        ):
            by_period.setdefault(str(item.get("period_end")), item)
        ordered = sorted(by_period.values(), key=lambda fact: str(fact.get("period_end")))
        if len(ordered) < 2:
            return None
        previous, current = ordered[-2], ordered[-1]
        return (previous, current) if compatible(previous, current) else None

    output: list[tuple[dict, dict]] = []
    for items in grouped.values():
        by_document: dict[str, list[dict]] = {}
        for item in items:
            by_document.setdefault(str(item.get("document") or ""), []).append(item)
        same_document = [pair for group in by_document.values() if (pair := choose(group))]
        pair = max(same_document, key=lambda value: str(value[1].get("period_end"))) if same_document else choose(items)
        if pair:
            output.append(pair)
        if len(output) == limit:
            break
    return output


def paired_rungs_chart(facts: list[dict]) -> str | None:
    """F6 Paired Rungs with explicit values, periods and deterministic deltas."""
    pairs = comparison_pairs(facts)
    if not pairs:
        return None

    def base_value(item: dict) -> Decimal:
        return Decimal(str(item["value"])) * Decimal(int(item.get("unit_scale") or 1))

    def period_label(item: dict) -> str:
        period = str(item.get("period_end") or "")
        return period[:4] if period.endswith("-12-31") else period

    height = 44 + len(pairs) * 104
    marks: list[str] = []
    for index, (previous, current) in enumerate(pairs):
        y = 32 + index * 104
        previous_value, current_value = base_value(previous), base_value(current)
        maximum = max(abs(previous_value), abs(current_value), Decimal(1))
        previous_width = max(4, int(335 * abs(previous_value) / maximum))
        current_width = max(4, int(335 * abs(current_value) / maximum))
        label = str(current.get("label") or current.get("metric_code") or "Показатель")
        short_label = label if len(label) <= 39 else f"{label[:38]}…"
        metric = str(current.get("metric_code") or "").lower()
        currency = str(current.get("currency") or "").upper()
        if metric in PERCENT_METRICS or currency in {"%", "PERCENT"}:
            delta = Decimal(str(current["value"])) - Decimal(str(previous["value"]))
            delta_label = f"{format_number(delta.copy_abs())} п.п."
            delta_class = "up" if delta > 0 else "down" if delta < 0 else "flat"
            delta_prefix = "+" if delta > 0 else "−" if delta < 0 else ""
        elif previous_value:
            delta = (current_value - previous_value) / abs(previous_value) * Decimal(100)
            delta_label = f"{format_number(delta.copy_abs().quantize(Decimal('0.1')))}%"
            delta_class = "up" if delta > 0 else "down" if delta < 0 else "flat"
            delta_prefix = "+" if delta > 0 else "−" if delta < 0 else ""
        else:
            delta_label, delta_class, delta_prefix = "н/д", "flat", ""
        marks.extend(
            [
                f'<text x="0" y="{y}" class="label"><title>{escape(label)}</title>{escape(short_label)}</text>',
                f'<rect x="250" y="{y + 13}" width="335" height="12" rx="6" class="track"/>',
                f'<rect x="250" y="{y + 13}" width="{previous_width}" height="12" rx="6" class="bar rung previous" data-fact-id="{escape(str(previous["id"]))}"/>',
                f'<text x="600" y="{y + 23}" class="period">{escape(period_label(previous))}</text>',
                f'<text x="720" y="{y + 23}" text-anchor="end" class="value">{escape(format_fact_value(previous))}</text>',
                f'<rect x="250" y="{y + 42}" width="335" height="12" rx="6" class="track"/>',
                f'<rect x="250" y="{y + 42}" width="{current_width}" height="12" rx="6" class="bar rung current" data-fact-id="{escape(str(current["id"]))}"/>',
                f'<text x="600" y="{y + 52}" class="period current-period">{escape(period_label(current))}</text>',
                f'<text x="720" y="{y + 52}" text-anchor="end" class="value current-value">{escape(format_fact_value(current))}</text>',
                f'<text x="250" y="{y + 78}" class="delta {delta_class}">ИЗМЕНЕНИЕ {escape(delta_prefix + delta_label)}</text>',
                f'<line x1="0" y1="{y + 91}" x2="720" y2="{y + 91}" class="baseline"/>',
            ]
        )
    return (
        '<svg class="lieflat-chart paired-rungs" data-template="F6" '
        f'data-gallery="templates/basics-gallery.html" viewBox="0 0 720 {height}" role="img" '
        'aria-label="Сравнение финансовых показателей: предыдущий и текущий периоды">'
        '<style>.paired-rungs text{font-family:Inter,system-ui,sans-serif;fill:var(--ink,var(--txt,#17211d))}'
        '.paired-rungs .previous{fill:var(--faint);opacity:.8}'
        '.paired-rungs .current{fill:var(--accent,var(--data,var(--ink,#176b5b)))}'
        '.paired-rungs .track{fill:var(--track,var(--quiet,var(--grid,#e9ece9)))}'
        '.paired-rungs .value{font-size:11px;font-weight:700}'
        '.paired-rungs .current-value{font-weight:850}.paired-rungs .period{font-size:9px;fill:var(--muted)}'
        '.paired-rungs .period{fill:var(--muted,var(--mut,#66706b))}'
        '.paired-rungs .current-period{fill:var(--accent,var(--data,var(--ink,#176b5b)));font-weight:800}'
        '.paired-rungs .delta{font-size:9px;font-weight:800}'
        '.paired-rungs .delta.up{fill:var(--accent,var(--data,var(--ink,#176b5b)))}'
        '.paired-rungs .delta.down{fill:var(--danger,#a84c43)}'
        '.paired-rungs .delta.flat{fill:var(--muted,var(--mut,#66706b))}'
        '.paired-rungs .label{font-size:11px;font-weight:750}'
        '.paired-rungs .baseline{stroke:var(--grid);stroke-width:1}</style>'
        + "".join(marks)
        + '</svg>'
    )


def rung_chart(facts: list[dict], chart_id: str) -> str:
    """Render a restrained Lieflat-compatible horizontal comparison chart."""
    if chart_id == "F6":
        paired = paired_rungs_chart(facts)
        if paired:
            return paired
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
        ".lieflat-chart text{font:13px ui-sans-serif,system-ui,sans-serif;fill:var(--ink,var(--txt,#17211d))}"
        ".lieflat-chart .label{font-weight:650}.lieflat-chart .value{font-size:14px;font-weight:800}"
        ".lieflat-chart .period{font-size:9px;fill:var(--muted,var(--mut,#66706b))}"
        ".lieflat-chart .track{fill:var(--track,var(--quiet,var(--grid,#e9ece9)))}"
        ".lieflat-chart .bar{fill:var(--accent,var(--data,var(--ink,#176b5b)))}"
        ".lieflat-chart .bar.negative{fill:var(--danger,#a84c43)}</style>"
        + "".join(marks)
        + "</svg>"
    )


def trend_series(facts: list[dict], limit: int = 3) -> list[list[dict]]:
    """Select metrics with at least three dated observations for small-multiple trends."""
    grouped: dict[str, list[dict]] = {}
    for item in facts:
        if item.get("period_end"):
            grouped.setdefault(str(item.get("metric_code") or item.get("label")), []).append(item)
    output: list[list[dict]] = []
    for items in grouped.values():
        by_period: dict[str, dict] = {}
        for item in sorted(items, key=lambda fact: str(fact.get("period_end"))):
            by_period[str(item.get("period_end"))] = item
        ordered = list(by_period.values())
        if len(ordered) >= 3:
            output.append(ordered[-8:])
        if len(output) == limit:
            break
    return output


def trend_chart(facts: list[dict]) -> str | None:
    """Render readable independent-scale small multiples for time-series questions."""
    series = trend_series(facts)
    if not series:
        return None
    row_height, width = 190, 900
    height = row_height * len(series)
    marks: list[str] = []
    for row, items in enumerate(series):
        top = row * row_height
        values = [Decimal(str(item["value"])) * Decimal(int(item.get("unit_scale") or 1)) for item in items]
        minimum, maximum = min(values), max(values)
        span = maximum - minimum or Decimal(1)
        step = Decimal(680) / Decimal(max(1, len(items) - 1))
        points: list[tuple[Decimal, Decimal]] = []
        for index, value in enumerate(values):
            x = Decimal(165) + step * Decimal(index)
            y = Decimal(top + 132) - (value - minimum) / span * Decimal(82)
            points.append((x, y))
        path = " ".join(
            f"{'M' if index == 0 else 'L'} {format(x, '.2f')} {format(y, '.2f')}"
            for index, (x, y) in enumerate(points)
        )
        label = str(items[-1].get("label") or items[-1].get("metric_code") or "Показатель")
        first, last = values[0], values[-1]
        change = (last - first) / abs(first) * Decimal(100) if first else None
        delta = (
            f"{'+' if change > 0 else '−' if change < 0 else ''}{format_number(change.copy_abs().quantize(Decimal('0.1')))}%"
            if change is not None
            else "н/д"
        )
        marks.extend(
            [
                f'<text x="0" y="{top + 26}" class="series-label">{escape(label)}</text>',
                f'<text x="900" y="{top + 26}" text-anchor="end" class="series-delta">{escape(delta)}</text>',
                f'<line x1="165" y1="{top + 132}" x2="845" y2="{top + 132}" class="axis"/>',
                f'<path d="{path}" class="trend-line" fill="none"/>',
            ]
        )
        for item, (x, y) in zip(items, points, strict=True):
            period = str(item.get("period_end"))
            period_label = period[:4] if period.endswith("-12-31") else period[:7]
            marks.extend(
                [
                    f'<circle cx="{x}" cy="{y}" r="5" class="trend-point" data-fact-id="{escape(str(item["id"]))}"/>',
                    f'<text x="{x}" y="{y - Decimal(13)}" text-anchor="middle" class="point-value">{escape(format_fact_value(item))}</text>',
                    f'<text x="{x}" y="{top + 154}" text-anchor="middle" class="period-label">{escape(period_label)}</text>',
                ]
            )
    return (
        f'<svg class="report-chart trend-chart" data-template="TREND" viewBox="0 0 {width} {height}" '
        'role="img" aria-label="Динамика финансовых показателей по периодам"><style>'
        '.trend-chart text{font-family:Inter,system-ui,sans-serif;fill:#17211d}'
        '.trend-chart .series-label{font-size:15px;font-weight:800}.trend-chart .series-delta{font-size:15px;font-weight:850;fill:#176b5b}'
        '.trend-chart .axis{stroke:#d9dedb}.trend-chart .trend-line{stroke:#176b5b;stroke-width:4;stroke-linecap:round;stroke-linejoin:round}'
        '.trend-chart .trend-point{fill:#fff;stroke:#176b5b;stroke-width:4}.trend-chart .point-value{font-size:11px;font-weight:750}'
        '.trend-chart .period-label{font-size:10px;fill:#66706b}</style>'
        + "".join(marks)
        + "</svg>"
    )


def entity_comparison_groups(facts: list[dict], limit: int = 4) -> list[list[dict]]:
    """Group the same metric and period across two or more banks/documents."""
    grouped: dict[tuple[str, str], dict[str, dict]] = {}
    for item in facts:
        period = str(item.get("period_end") or "")
        entity = str(item.get("entity") or item.get("document") or "")
        if not period or not entity:
            continue
        key = (str(item.get("metric_code") or item.get("label")), period)
        grouped.setdefault(key, {}).setdefault(entity, item)
    groups = [list(entities.values()) for entities in grouped.values() if len(entities) >= 2]
    return groups[:limit]


def entity_comparison_chart(facts: list[dict]) -> str | None:
    groups = entity_comparison_groups(facts)
    if not groups:
        return None
    row_height = 58
    height = 42 + sum(42 + len(group) * row_height for group in groups)
    marks: list[str] = []
    y = 25
    for group in groups:
        label = str(group[0].get("label") or group[0].get("metric_code") or "Показатель")
        marks.append(f'<text x="0" y="{y}" class="metric-label">{escape(label)}</text>')
        y += 24
        values = [abs(Decimal(str(item["value"])) * Decimal(int(item.get("unit_scale") or 1))) for item in group]
        maximum = max(values or [Decimal(1)]) or Decimal(1)
        for item, value in zip(group, values, strict=True):
            bar_width = max(5, int(500 * value / maximum))
            entity = str(item.get("entity") or item.get("document"))
            short_entity = entity if len(entity) <= 34 else f"{entity[:33]}…"
            marks.extend(
                [
                    f'<text x="0" y="{y + 16}" class="entity-label"><title>{escape(entity)}</title>{escape(short_entity)}</text>',
                    f'<rect x="250" y="{y}" width="500" height="22" rx="5" class="track"/>',
                    f'<rect x="250" y="{y}" width="{bar_width}" height="22" rx="5" class="entity-bar" data-fact-id="{escape(str(item["id"]))}"/>',
                    f'<text x="880" y="{y + 16}" text-anchor="end" class="entity-value">{escape(format_fact_value(item))}</text>',
                ]
            )
            y += row_height
        y += 18
    return (
        f'<svg class="report-chart entity-chart" data-template="ENTITY-COMPARE" viewBox="0 0 900 {height}" '
        'role="img" aria-label="Сравнение показателей банков"><style>'
        '.entity-chart text{font-family:Inter,system-ui,sans-serif;fill:#17211d}.entity-chart .metric-label{font-size:15px;font-weight:850}'
        '.entity-chart .entity-label{font-size:11px;font-weight:700}.entity-chart .entity-value{font-size:12px;font-weight:800}'
        '.entity-chart .track{fill:#e9ece9}.entity-chart .entity-bar{fill:#176b5b}</style>'
        + "".join(marks)
        + "</svg>"
    )
