import json
from pathlib import Path
from validation.validator import validate_intent, IntentValidationError


def load_config():
    return json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))


def assert_validated(intent, config):
    validated = validate_intent(intent, config)
    assert "resolved_dates" in validated
    rd = validated["resolved_dates"]
    assert "start_date" in rd and "end_date" in rd
    return validated


def test_trend_by_region_last_6_months():
    config = load_config()
    intent = {"metric": "revenue", "filters": {}, "group_by": "region", "date_range": "last_6_months"}
    validated = assert_validated(intent, config)
    assert validated.get("group_by") == "region"


def test_trend_by_product_last_3_months():
    config = load_config()
    intent = {"metric": "revenue", "filters": {}, "group_by": "product_name", "date_range": "last_3_months"}
    validated = assert_validated(intent, config)
    assert validated.get("group_by") == "product_name"


def test_trend_by_sales_rep_last_6_months():
    config = load_config()
    intent = {"metric": "revenue", "filters": {"sales_rep": "Helena Gomez"}, "group_by": "month", "date_range": "last_6_months"}
    validated = assert_validated(intent, config)
    assert "sales_rep" in validated.get("filters", {})


def test_trend_by_pipeline_state_custom_period():
    config = load_config()
    # Use a custom month period supported by the date resolver
    intent = {
        "metric": "revenue",
        "filters": {"pipeline_stage": "closed_won"},
        "group_by": "month",
        "date_range": "last_12_months",
    }
    validated = assert_validated(intent, config)
    assert "pipeline_stage" in validated.get("filters", {})


def test_custom_month_period_resolution():
    config = load_config()
    intent = {"metric": "revenue", "filters": {}, "group_by": None, "custom_date": {"month": "2025-08"}}
    validated = assert_validated(intent, config)
    rd = validated["resolved_dates"]
    assert rd["start_date"].startswith("2025-08")
