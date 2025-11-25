import pytest
from nlp.validator import validate_intent


@pytest.fixture
def sample_config():
    return {
        "metrics": {"revenue": "net_revenue", "deal_count": "COUNT(*)"},
        "dimensions": {"region": "country", "sales_rep": "rep_name", "product_name": "product_name"},
        "date_ranges": {"last_12_months": 365, "last_6_months": 182},
    }


def test_validate_valid_intent(sample_config):
    intent = {"metric": "revenue", "filters": {"region": "EMEA"}, "group_by": None, "date_range": "last_6_months"}
    # should not raise
    validate_intent(intent, sample_config)


def test_validate_invalid_metric_raises(sample_config):
    intent = {"metric": "profit", "filters": {}, "group_by": None, "date_range": "last_6_months"}
    with pytest.raises(RuntimeError):
        validate_intent(intent, sample_config)


def test_validate_invalid_filter_raises(sample_config):
    intent = {"metric": "revenue", "filters": {"unknown_dim": "x"}, "group_by": None, "date_range": "last_6_months"}
    with pytest.raises(RuntimeError):
        validate_intent(intent, sample_config)


def test_validate_invalid_group_by_raises(sample_config):
    intent = {"metric": "revenue", "filters": {}, "group_by": "not_a_dim", "date_range": "last_6_months"}
    with pytest.raises(RuntimeError):
        validate_intent(intent, sample_config)


def test_validate_invalid_date_range_raises(sample_config):
    intent = {"metric": "revenue", "filters": {}, "group_by": None, "date_range": "last_5_months"}
    with pytest.raises(RuntimeError):
        validate_intent(intent, sample_config)
