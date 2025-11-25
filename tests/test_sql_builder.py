import json
from pathlib import Path
from builder.sql_builder import build_sql


def load_config():
    return json.loads(Path('config_store/tenant1.json').read_text(encoding='utf-8-sig'))


def test_build_summary_sql_sqlite():
    cfg = load_config()
    intent = {
        "metric": "revenue",
        "filters": {},
        "group_by": None,
        "resolved_dates": {"start_date": "2024-11-22", "end_date": "2025-11-22"}
    }
    sel, params = build_sql(intent, cfg, db_type='sqlite')
    
    # Verify params are returned correctly
    assert "start_date" in params
    assert "end_date" in params
    assert params["start_date"] == "2024-11-22"
    assert params["end_date"] == "2025-11-22"
    
    # Compile without literal_binds and check structure
    from sqlalchemy import create_engine
    engine = create_engine("sqlite://")
    compiled = sel.compile(dialect=engine.dialect)
    sql = str(compiled)
    assert 'fact_sales_pipeline' in sql
    assert "net_revenue" in sql or "SUM" in sql.upper()


def test_build_group_by_sql_sqlite():
    cfg = load_config()
    intent = {
        "metric": "revenue",
        "filters": {},
        "group_by": "product_name",
        "resolved_dates": {"start_date": "2024-11-22", "end_date": "2025-11-22"}
    }
    sel, params = build_sql(intent, cfg, db_type='sqlite')
    
    # Verify params
    assert "start_date" in params
    assert "end_date" in params
    
    from sqlalchemy import create_engine
    engine = create_engine("sqlite://")
    compiled = sel.compile(dialect=engine.dialect)
    sql = str(compiled)
    assert 'GROUP BY' in sql.upper()
    assert 'product_name' in sql
