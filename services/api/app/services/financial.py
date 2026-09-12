import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from statistics import median


TAXONOMY: dict[str, tuple[str, ...]] = {
    "assets": ("активы", "total assets", "итого активов"),
    "equity": ("капитал", "equity", "собственные средства"),
    "net_profit": ("чистая прибыль", "net profit", "прибыль за период"),
    "net_interest_income": ("чистые процентные доходы", "net interest income"),
    "fee_income": ("чистые комиссионные доходы", "net fee", "commission income"),
    "provisions": ("резерв", "credit loss", "обесценен"),
    "loans": ("кредиты клиентам", "loans to customers", "кредитный портфель"),
    "customer_funds": ("средства клиентов", "customer accounts", "customer funds"),
    "npl": ("просроч", "non-performing", "npl"),
    "capital_adequacy": ("достаточност", "capital adequacy", "н1.0"),
    "roa": ("рентабельность активов", "return on assets", "roa"),
    "roe": ("рентабельность капитала", "return on equity", "roe"),
}


@dataclass(frozen=True)
class MetricCandidate:
    metric_code: str
    label: str
    value: Decimal
    confidence: str
    location: dict


def parse_decimal(raw: str) -> Decimal | None:
    text = str(raw).strip().replace("\u00a0", "").replace(" ", "").replace("−", "-")
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("%", "").replace(",", ".")
    text = re.sub(r"[^\d.\-]", "", text)
    if text.count(".") > 1:
        text = text.replace(".", "", text.count(".") - 1)
    try:
        value = Decimal(text)
        return -value if negative else value
    except InvalidOperation:
        return None


def map_candidates(items: list[dict]) -> list[MetricCandidate]:
    mapped: list[MetricCandidate] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        label = str(item.get("label", "")).strip()
        lowered = label.casefold()
        value = parse_decimal(str(item.get("value", "")))
        if value is None:
            continue
        for code, aliases in TAXONOMY.items():
            if any(alias in lowered for alias in aliases):
                key = (code, str(value))
                if key not in seen:
                    mapped.append(
                        MetricCandidate(
                            code,
                            label,
                            value,
                            "medium",
                            {k: v for k, v in item.items() if k not in {"label", "value"}},
                        )
                    )
                    seen.add(key)
                break
    return mapped


def growth(current: Decimal, previous: Decimal) -> Decimal | None:
    if previous == 0:
        return None
    return ((current - previous) / abs(previous) * Decimal(100)).quantize(Decimal("0.01"))


def ratio(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    return (numerator / denominator * Decimal(100)).quantize(Decimal("0.01"))


def forecast_lag_days(historical_lags: list[int]) -> int | None:
    if len(historical_lags) < 3:
        return None
    return int(median(historical_lags[-6:]))
