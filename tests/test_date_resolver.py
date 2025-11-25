from nlp.date_resolver import resolve_date_range


def test_resolve_last_5_months_maps_to_last_6_months():
    config = {"date_ranges": {"last_12_months": 365, "last_6_months": 182, "last_3_months": 90}}
    key, auto = resolve_date_range("last 5 months", config)
    assert key == "last_6_months"
    assert auto is True


def test_resolve_explicit_last_6_months_not_auto():
    config = {"date_ranges": {"last_12_months": 365, "last_6_months": 182, "last_3_months": 90}}
    key, auto = resolve_date_range("last 6 months", config)
    assert key == "last_6_months"
    assert auto is False


def test_empty_question_returns_first_allowed():
    config = {"date_ranges": {"last_12_months": 365, "last_6_months": 182}}
    key, auto = resolve_date_range("", config)
    # Implementation returns the first allowed key when question is empty
    assert key == "last_12_months"
    assert auto is False
