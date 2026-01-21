"""
Acceptance tests for the end-to-end NL→SQL pipeline.

These tests validate:
1. Schema extraction produces expected structure
2. Parser few-shot examples parse to exact JSON
3. Builder produces parameterized SQL with correct structure
4. Known queries execute and return expected row counts
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest


def test_schema_json_exists_and_valid():
    """Verify tenant1_db_schema.json exists and contains expected tables."""
    schema_path = Path("config_store/tenant1_db_schema.json")
    assert schema_path.exists(), "Schema JSON not found"
    
    schema = json.loads(schema_path.read_text(encoding="utf-8-sig"))
    assert "tables" in schema
    assert "fact_sales_pipeline" in schema["tables"]
    
    fact_meta = schema["tables"]["fact_sales_pipeline"]
    col_names = [c["name"] for c in fact_meta["columns"]]
    
    # Verify key columns exist
    assert "region_id" in col_names
    assert "sales_rep_id" in col_names
    assert "net_revenue" in col_names
    assert "sale_date" in col_names


def test_parser_few_shot_examples():
    """Verify the parser correctly handles the few-shot examples from the system prompt."""
    from nlp.llm_intent_parser import parse_intent_with_llm
    
    config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))
    
    # Example 1: monthly revenue for sales rep Carlos Martinez for last 6 months
    intent1 = parse_intent_with_llm("monthly revenue for sales rep Carlos Martinez for last 6 months", config)
    assert intent1["metric"] == "revenue"
    assert intent1["filters"] == {"sales_rep": "Carlos Martinez"}
    assert intent1["group_by"] == "month"
    assert intent1["date_range"] == "last_6_months"
    
    # Example 2: revenue from EMEA region for last year (should map to last_12_months)
    intent2 = parse_intent_with_llm("revenue from EMEA region for last year", config)
    assert intent2["metric"] == "revenue"
    assert intent2["filters"]["region"] == "EMEA"
    assert intent2["group_by"] is None
    assert intent2["date_range"] == "last_12_months"


def test_builder_returns_parameterized_sql():
    """Verify the SQL builder returns a Select object and params dict."""
    from builder.sql_builder import build_sql
    from sqlalchemy.sql.selectable import Select
    
    config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))
    
    intent = {
        "metric": "revenue",
        "filters": {"region": "EMEA"},
        "group_by": None,
        "date_range": "last_12_months",
        "resolved_dates": {"start_date": "2024-11-24", "end_date": "2025-11-24"}
    }
    
    sel, params = build_sql(intent, config)
    
    assert isinstance(sel, Select), "Builder should return a Select object"
    assert isinstance(params, dict), "Builder should return params dict"
    assert "start_date" in params
    assert "end_date" in params
    assert "region" in params


def test_canonical_query_execution():
    """Execute a canonical query and verify it returns expected structure."""
    from nlp.llm_intent_parser import parse_intent_with_llm
    from validation.validator import validate_intent
    from builder.sql_builder import build_sql
    from sqlalchemy import create_engine
    
    config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))
    
    # Parse a simple query
    intent = parse_intent_with_llm("total revenue for last 12 months", config)
    validated = validate_intent(intent, config)
    sel, params = build_sql(validated, config)
    
    # Execute
    engine = create_engine('sqlite:///enhanced_sales.db')
    conn = engine.connect()
    res = conn.execute(sel, params)
    rows = [dict(r._mapping) for r in res]
    conn.close()
    
    # Verify structure
    assert len(rows) == 1, "Summary query should return one row"
    assert "metric" in rows[0], "Result should have metric column"
    assert isinstance(rows[0]["metric"], (int, float)), "Metric should be numeric"


def test_trend_query_execution():
    """Execute a trend query and verify it returns multiple months."""
    from nlp.llm_intent_parser import parse_intent_with_llm
    from validation.validator import validate_intent
    from builder.sql_builder import build_sql
    from sqlalchemy import create_engine
    
    config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))
    
    # Parse monthly trend query
    intent = parse_intent_with_llm("monthly revenue for last 6 months", config)
    validated = validate_intent(intent, config)
    sel, params = build_sql(validated, config)
    
    # Execute
    engine = create_engine('sqlite:///enhanced_sales.db')
    conn = engine.connect()
    res = conn.execute(sel, params)
    rows = [dict(r._mapping) for r in res]
    conn.close()
    
    # Verify structure
    assert len(rows) > 0, "Trend query should return rows"
    assert "month" in rows[0], "Result should have month column"
    assert "metric" in rows[0], "Result should have metric column"


def test_group_by_query_execution():
    """Execute a group_by query and verify it groups correctly."""
    from nlp.llm_intent_parser import parse_intent_with_llm
    from validation.validator import validate_intent
    from builder.sql_builder import build_sql
    from sqlalchemy import create_engine
    
    config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))
    
    # Parse group_by query
    intent = parse_intent_with_llm("revenue by region for last 12 months", config)
    validated = validate_intent(intent, config)
    sel, params = build_sql(validated, config)
    
    # Execute
    engine = create_engine('sqlite:///enhanced_sales.db')
    conn = engine.connect()
    res = conn.execute(sel, params)
    rows = [dict(r._mapping) for r in res]
    conn.close()
    
    # Verify structure
    assert len(rows) > 0, "Group by query should return rows"
    assert "group_col" in rows[0], "Result should have group_col"
    assert "metric" in rows[0], "Result should have metric column"


def test_product_category_grouping_executes():
    """Execute a product category grouping query to ensure category mapping works."""
    from nlp.llm_intent_parser import parse_intent_with_llm
    from validation.validator import validate_intent
    from builder.sql_builder import build_sql
    from sqlalchemy import create_engine

    config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))

    intent = parse_intent_with_llm("revenue by product category for last 12 months", config)
    validated = validate_intent(intent, config)
    sel, params = build_sql(validated, config)

    engine = create_engine('sqlite:///enhanced_sales.db')
    conn = engine.connect()
    res = conn.execute(sel, params)
    rows = [dict(r._mapping) for r in res]
    conn.close()

    assert len(rows) > 0, "Category grouping should return rows"
    assert "group_col" in rows[0], "Result should include group_col"
    assert "metric" in rows[0], "Result should include metric"


def test_date_normalization():
    """Verify date phrase normalization works."""
    from nlp.llm_intent_parser import parse_intent_with_llm
    
    config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))
    
    # Test "last year" normalizes to "last 12 months"
    intent = parse_intent_with_llm("revenue for last year", config)
    assert intent["date_range"] == "last_12_months"
    
    # Test "past 2 years" normalizes to "last 24 months"
    intent2 = parse_intent_with_llm("revenue for past 2 years", config)
    assert intent2["date_range"] == "last_24_months"


def test_top_n_ignored():
    """Verify 'Top N' modifiers are ignored and group_by is used."""
    from nlp.llm_intent_parser import parse_intent_with_llm
    
    config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))
    
    # "Top 5 customers" should parse as group_by customer_name
    intent = parse_intent_with_llm("Top 5 customers by revenue for last 12 months", config)
    assert intent["metric"] == "revenue"
    assert intent["group_by"] == "customer_name"
    assert intent["date_range"] == "last_12_months"
