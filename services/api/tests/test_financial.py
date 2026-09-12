from decimal import Decimal

from app.services.financial import forecast_lag_days, growth, map_candidates, ratio


def test_decimal_calculations_are_exact():
    assert growth(Decimal("120"), Decimal("100")) == Decimal("20.00")
    assert growth(Decimal("10"), Decimal("0")) is None
    assert ratio(Decimal("5"), Decimal("20")) == Decimal("25.00")


def test_taxonomy_mapping_keeps_provenance_location():
    result = map_candidates([{"label": "Чистая прибыль", "value": "1 250,50", "page": 7}])
    assert len(result) == 1
    assert result[0].metric_code == "net_profit"
    assert result[0].value == Decimal("1250.50")
    assert result[0].location["page"] == 7


def test_taxonomy_prefers_specific_ratio_over_equity_substring():
    result = map_candidates(
        [
            {"label": "Достаточность капитала", "value": "14,7"},
            {"label": "Рентабельность капитала", "value": "21,2"},
        ]
    )
    assert [item.metric_code for item in result] == ["capital_adequacy", "roe"]


def test_forecast_requires_three_observations():
    assert forecast_lag_days([40, 42]) is None
    assert forecast_lag_days([40, 42, 41]) == 41
