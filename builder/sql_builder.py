"""SQL builder using SQLAlchemy Core.

This replaces the previous template-based renderer with a programmatic
SQLAlchemy Core implementation that builds parameterized SQL and is easier
to adapt to multiple dialects.
"""
from __future__ import annotations

import json
from typing import Dict, Any, Optional, List, Tuple
from sqlalchemy import Table, MetaData, select, func, literal_column, text
from sqlalchemy.engine import default
import sqlite3
from pathlib import Path


class SQLBuilderError(ValueError):
    pass


_SCHEMA_CACHE: Optional[Dict[str, Any]] = None


def _load_schema(schema_path: str = "config_store/tenant1_db_schema.json") -> Dict[str, Any]:
    """Load the extracted DB schema JSON. Cache it in memory for performance.
    
    Returns empty dict if schema file doesn't exist (fallback to PRAGMA-based discovery).
    """
    global _SCHEMA_CACHE
    if _SCHEMA_CACHE is not None:
        return _SCHEMA_CACHE
    
    p = Path(schema_path)
    if not p.exists():
        return {}
    
    try:
        _SCHEMA_CACHE = json.loads(p.read_text(encoding="utf-8-sig"))
        return _SCHEMA_CACHE
    except Exception:
        return {}


def _get_table_columns(table_name: str, schema: Dict[str, Any]) -> List[str]:
    """Get column names for a table from schema JSON."""
    tables = schema.get("tables", {})
    meta = tables.get(table_name, {})
    return [c["name"] for c in meta.get("columns", [])]


def _find_join_key(fact_table: str, dim_table: str, fact_cols: List[str], schema: Dict[str, Any]) -> Optional[str]:
    """Find the join key between fact and dim table using declared FKs first, then inferred, then heuristics."""
    tables = schema.get("tables", {})
    fact_meta = tables.get(fact_table, {})
    
    # Check declared foreign keys
    for fk in fact_meta.get("declared_foreign_keys", []):
        if fk.get("ref_table") == dim_table and fk.get("column") in fact_cols:
            return fk["column"]
    
    # Check inferred foreign keys
    for fk in fact_meta.get("inferred_foreign_keys", []):
        if fk.get("ref_table") == dim_table and fk.get("column") in fact_cols:
            return fk["column"]
    
    # Heuristic fallback: look for {dim_base}_id in fact_cols
    base = dim_table.replace("dim_", "")
    candidate = f"{base}_id"
    if candidate in fact_cols:
        return candidate
    
    return None


def _find_dim_table_for_column(column_name: str, schema: Dict[str, Any]) -> Optional[str]:
    """Find which dim_* table contains the given column."""
    tables = schema.get("tables", {})
    for tname, meta in tables.items():
        if not tname.startswith("dim_"):
            continue
        cols = [c["name"] for c in meta.get("columns", [])]
        if column_name in cols:
            return tname
    return None


def build_sql(intent: Dict[str, Any], config: Dict[str, Any], db_type: str = "sqlite") -> str:
    """Build a SQL string for the given validated intent and tenant config.

    Returns the SQL string with literal bounds substituted (useful for
    executing on sqlite; for production you should execute via parameterized
    statements using SQLAlchemy engine and bind parameters).
    """
    db_type = db_type.lower()
    # We support any dialect SQLAlchemy knows about; for now accept sqlite
    if db_type not in ("sqlite", "postgresql", "mysql", "mssql"):
        raise SQLBuilderError(f"Unsupported db_type: {db_type}")

    strategy = _determine_strategy(intent)

    metric_name = intent["metric"]
    if metric_name not in config.get("metrics", {}):
        raise SQLBuilderError(f"Unknown metric: {metric_name}")
    metric_formula = config["metrics"][metric_name]

    fact_table = config["fact_table"]
    date_column = config["date_column"]
    start_date = intent["resolved_dates"]["start_date"]
    end_date = intent["resolved_dates"]["end_date"]

    metadata = MetaData()
    # NOTE: we only use the table object for column expression convenience in more complex setups
    _ = Table(fact_table, metadata)

    # Load schema from JSON (with fallback to PRAGMA if unavailable)
    schema = _load_schema()
    fact_cols = _get_table_columns(fact_table, schema) if schema else []
    
    # Fallback to PRAGMA if schema JSON not available
    if not fact_cols:
        db_path = Path("enhanced_sales.db")
        if db_path.exists():
            try:
                with sqlite3.connect(str(db_path)) as conn:
                    cur = conn.cursor()
                    cur.execute(f"PRAGMA table_info('{fact_table}')")
                    fact_cols = [r[1] for r in cur.fetchall()]
            except Exception:
                fact_cols = []

    # map group_by to actual column name from config
    group_by = intent.get("group_by")
    # treat the special 'month' group_by as a temporal expression, not a column
    group_col = None if group_by == "month" else (_map_dimension(group_by, config) if group_by else None)

    # choose an aggregation expression for the requested metric
    mf = metric_formula.strip()
    if mf.upper().startswith("COUNT("):
        # handle COUNT(*) or COUNT(col)
        inner = mf[mf.find("(") + 1: mf.rfind(")")].strip()
        if inner == "*" or inner == "":
            metric_expr = func.count().label("metric")
        else:
            metric_expr = func.count(text(inner)).label("metric")
    elif mf.upper().startswith("AVG("):
        inner = mf[mf.find("(") + 1: mf.rfind(")")].strip()
        metric_expr = func.avg(text(inner)).label("metric")
    else:
        # default to SUM
        metric_expr = func.sum(text(metric_formula)).label("metric")

    # Build base select depending on strategy
    if strategy == "trend":
        # group by month (use the same expression object for select and group_by)
        month_expr = func.strftime("%Y-%m", literal_column(f"f.{date_column}")).label("month")

        # prepare from / join clauses to support filters that live in dim tables
        from_clause = f"{fact_table} f"
        join_clauses = []
        where_clauses = [f"f.{date_column} >= :start_date", f"f.{date_column} <= :end_date"]
        dim_alias_counter = 0
        for col, val in (intent.get("filters") or {}).items():
            mapped = _map_dimension(col, config) or col
            if mapped in fact_cols:
                where_clauses.append(f"f.{mapped} = :{col}")
            else:
                # search dim tables for this mapped column using schema JSON
                dim_table = _find_dim_table_for_column(mapped, schema) if schema else None
                
                # Fallback to PRAGMA if schema not available
                if not dim_table:
                    db_path = Path("enhanced_sales.db")
                    if db_path.exists():
                        with sqlite3.connect(str(db_path)) as conn:
                            cur = conn.cursor()
                            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'dim_%'")
                            for (t,) in cur.fetchall():
                                cur.execute(f"PRAGMA table_info('{t}')")
                                cols = [r[1] for r in cur.fetchall()]
                                if mapped in cols:
                                    dim_table = t
                                    break
                
                if not dim_table:
                    where_clauses.append(f"f.{mapped} = :{col}")
                else:
                    # Find join key using schema (declared/inferred FKs) or heuristic
                    join_key = _find_join_key(fact_table, dim_table, fact_cols, schema) if schema else None
                    if not join_key:
                        candidate = dim_table.replace('dim_', '') + '_id'
                        if candidate in fact_cols:
                            join_key = candidate
                    if not join_key:
                        raise SQLBuilderError(f"Cannot determine join key between {fact_table} and {dim_table} for filter {col}")
                    dalias = f"d{dim_alias_counter}"
                    dim_alias_counter += 1
                    join_clauses.append(f"JOIN {dim_table} {dalias} ON f.{join_key} = {dalias}.{join_key}")
                    where_clauses.append(f"{dalias}.{mapped} = :{col}")

        sel = select(
            month_expr,
            literal_column("''").label("group_col") if not group_col else literal_column(f"f.{group_col}").label("group_col"),
            metric_expr
        ).select_from(text(" ".join([from_clause] + join_clauses)))
        for w in where_clauses:
            sel = sel.where(text(w))
        group_items = [month_expr]
        if group_col:
            group_items.append(literal_column(f"f.{group_col}"))
        sel = sel.group_by(*group_items).order_by(month_expr)

    elif strategy == "summary":
        # Build from/join/where for summary with filters possibly in dim tables
        from_clause = f"{fact_table} f"
        join_clauses = []
        where_clauses = [f"f.{date_column} >= :start_date", f"f.{date_column} <= :end_date"]
        dim_alias_counter = 0
        for col, val in (intent.get("filters") or {}).items():
            mapped = _map_dimension(col, config) or col
            if mapped in fact_cols:
                where_clauses.append(f"f.{mapped} = :{col}")
            else:
                # search dim tables for this mapped column using schema JSON
                dim_table = _find_dim_table_for_column(mapped, schema) if schema else None
                
                # Fallback to PRAGMA if schema not available
                if not dim_table:
                    db_path = Path("enhanced_sales.db")
                    if db_path.exists():
                        with sqlite3.connect(str(db_path)) as conn:
                            cur = conn.cursor()
                            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'dim_%'")
                            for (t,) in cur.fetchall():
                                cur.execute(f"PRAGMA table_info('{t}')")
                                cols = [r[1] for r in cur.fetchall()]
                                if mapped in cols:
                                    dim_table = t
                                    break
                
                if not dim_table:
                    where_clauses.append(f"f.{mapped} = :{col}")
                else:
                    # Find join key using schema (declared/inferred FKs) or heuristic
                    join_key = _find_join_key(fact_table, dim_table, fact_cols, schema) if schema else None
                    if not join_key:
                        candidate = dim_table.replace('dim_', '') + '_id'
                        if candidate in fact_cols:
                            join_key = candidate
                    if not join_key:
                        raise SQLBuilderError(f"Cannot determine join key between {fact_table} and {dim_table} for filter {col}")
                    dalias = f"d{dim_alias_counter}"
                    dim_alias_counter += 1
                    join_clauses.append(f"JOIN {dim_table} {dalias} ON f.{join_key} = {dalias}.{join_key}")
                    where_clauses.append(f"{dalias}.{mapped} = :{col}")

        sel = select(metric_expr).select_from(text(" ".join([from_clause] + join_clauses)));
        for w in where_clauses:
            sel = sel.where(text(w))

    else:  # group_by
        if not group_col:
            raise SQLBuilderError("group_by specified but cannot map to a dimension")

        # If the requested group column isn't present in the fact table,
        # attempt to find a dim_* table that contains it and join.
        if group_col in fact_cols:
            group_expr = literal_column(f"f.{group_col}")
            from_clause = f"{fact_table} f"
            join_clauses = []
            where_clauses = [f"f.{date_column} >= :start_date", f"f.{date_column} <= :end_date"]
            dim_alias_counter = 0
            for col, val in (intent.get("filters") or {}).items():
                mapped = _map_dimension(col, config) or col
                if mapped in fact_cols:
                    where_clauses.append(f"f.{mapped} = :{col}")
                else:
                    # search dim tables for this mapped column using schema JSON
                    dim_table = _find_dim_table_for_column(mapped, schema) if schema else None
                    
                    # Fallback to PRAGMA if schema not available
                    if not dim_table:
                        db_path = Path("enhanced_sales.db")
                        if db_path.exists():
                            with sqlite3.connect(str(db_path)) as conn:
                                cur = conn.cursor()
                                cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'dim_%'")
                                for (t,) in cur.fetchall():
                                    cur.execute(f"PRAGMA table_info('{t}')")
                                    cols = [r[1] for r in cur.fetchall()]
                                    if mapped in cols:
                                        dim_table = t
                                        break
                    
                    if not dim_table:
                        where_clauses.append(f"f.{mapped} = :{col}")
                    else:
                        # Find join key using schema (declared/inferred FKs) or heuristic
                        join_key = _find_join_key(fact_table, dim_table, fact_cols, schema) if schema else None
                        if not join_key:
                            candidate = dim_table.replace('dim_', '') + '_id'
                            if candidate in fact_cols:
                                join_key = candidate
                        if not join_key:
                            raise SQLBuilderError(f"Cannot determine join key between {fact_table} and {dim_table} for filter {col}")
                        dalias = f"d{dim_alias_counter}"
                        dim_alias_counter += 1
                        join_clauses.append(f"JOIN {dim_table} {dalias} ON f.{join_key} = {dalias}.{join_key}")
                        where_clauses.append(f"{dalias}.{mapped} = :{col}")

            sel = select(literal_column(f"f.{group_col}").label("group_col"), metric_expr).select_from(text(" ".join([from_clause] + join_clauses)))
            for w in where_clauses:
                sel = sel.where(text(w))
            sel = sel.group_by(literal_column(f"f.{group_col}")).order_by(text("metric DESC"))
        else:
            # group_col lives in a dim table; find it and join
            dim_table = _find_dim_table_for_column(group_col, schema) if schema else None
            
            # Fallback to PRAGMA if schema not available
            if not dim_table:
                db_path = Path("enhanced_sales.db")
                if db_path.exists():
                    with sqlite3.connect(str(db_path)) as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'dim_%'")
                        for (t,) in cur.fetchall():
                            cur.execute(f"PRAGMA table_info('{t}')")
                            cols = [r[1] for r in cur.fetchall()]
                            if group_col in cols:
                                dim_table = t
                                break

            if not dim_table:
                # fallback: treat as column on fact table (parameterized)
                sel = select(literal_column(group_col).label("group_col"), metric_expr).select_from(text(fact_table))
                sel = sel.where(text(f"{fact_table}.{date_column} >= :start_date")).where(text(f"{fact_table}.{date_column} <= :end_date"))
                for col, val in (intent.get("filters") or {}).items():
                    mapped = _map_dimension(col, config) or col
                    if mapped in fact_cols:
                        sel = sel.where(text(f"f.{mapped} = :{col}"))
                    else:
                        sel = sel.where(text(f"{mapped} = :{col}"))
                sel = sel.group_by(text(group_col)).order_by(text("metric DESC"))
            else:
                # Find join key using schema (declared/inferred FKs) or heuristic
                join_key = _find_join_key(fact_table, dim_table, fact_cols, schema) if schema else None
                if not join_key:
                    candidate = dim_table.replace('dim_', '') + '_id'
                    if candidate in fact_cols:
                        join_key = candidate
                if not join_key:
                    raise SQLBuilderError(f"Cannot determine join key between {fact_table} and {dim_table}")

                sel = select(literal_column(f"d.{group_col}").label("group_col"), metric_expr).select_from(text(f"{fact_table} f JOIN {dim_table} d ON f.{join_key} = d.{join_key}"))
                sel = sel.where(text(f"f.{date_column} >= :start_date")).where(text(f"f.{date_column} <= :end_date"))
                for col, val in (intent.get("filters") or {}).items():
                    mapped = _map_dimension(col, config) or col
                    if mapped in fact_cols:
                        sel = sel.where(text(f"f.{mapped} = :{col}"))
                    else:
                        # if filter lives in a dim table, attempt to find the dim and join it
                        sel = sel.where(text(f"d.{mapped} = :{col}"))
                sel = sel.group_by(literal_column(f"d.{group_col}")).order_by(text("metric DESC"))

    # Prepare params and bind them to the Select. Return the Select and params dict.
    params = {"start_date": start_date, "end_date": end_date}
    for col, val in (intent.get("filters") or {}).items():
        params[col] = val

    # Bind params into the Select for convenience (so callers can execute
    # the Select directly via SQLAlchemy engines or compile it with
    # literal_binds for debugging/tests).
    sel = sel.params(**params)

    return sel, params


def _determine_strategy(intent: Dict[str, Any]) -> str:
    if intent.get("group_by") in (None, "", "month"):
        if intent.get("group_by") == "month":
            return "trend"
        return "summary"
    return "group_by"


def _map_dimension(dimension: str | None, config: Dict[str, Any]) -> str:
    if not dimension:
        return ""
    return config["dimensions"].get(dimension, dimension)


__all__ = ["build_sql", "SQLBuilderError"]
