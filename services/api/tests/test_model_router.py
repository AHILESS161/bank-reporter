from app.services.model_router import ModelRouter


def test_finance_validation_rejects_unknown_fact_id():
    data = {
        "summary": "x",
        "highlights": [{"text": "x", "fact_ids": ["missing"]}],
        "risks": [],
        "chart": {"template": "F1", "metric_codes": []},
    }
    try:
        ModelRouter._validate_narrative(data, {"known"})
    except ValueError as exc:
        assert "fact_ids" in str(exc)
    else:
        raise AssertionError("validation must fail")


def test_deterministic_narrative_has_citations():
    result = ModelRouter._deterministic_narrative(
        [{"id": "f1", "label": "Активы", "value": "10", "metric_code": "assets"}]
    )
    assert result["highlights"][0]["fact_ids"] == ["f1"]
