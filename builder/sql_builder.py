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

    # Support ephemeral derived expressions without changing config
    derived_expr = intent.get("derived_expression")
    metric_name = intent["metric"]
    if derived_expr:
        metric_formula = derived_expr
    else:
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
    # Support both string and array group_by
    group_by = intent.get("group_by")
    if isinstance(group_by, list):
        # Multi-dimensional grouping: map each dimension
        group_cols = []
        for dim in group_by:
            if dim == "month":
                group_cols.append("month")  # special temporal marker
            else:
                mapped = _map_dimension(dim, config)
                group_cols.append(mapped if mapped else dim)
    elif group_by:
        # Single dimension grouping
        if group_by == "month":
            group_cols = ["month"]
        else:
            mapped_col = _map_dimension(group_by, config)
            group_cols = [mapped_col if mapped_col else group_by]
    else:
        group_cols = []
    
    # For legacy code that uses group_col (singular), extract first dimension if not "month"
    group_col = None if not group_cols or group_cols[0] == "month" else group_cols[0]

    # choose an aggregation expression for the requested metric
    mf = metric_formula.strip()
    mf_upper = mf.upper()
    if derived_expr:
        # Use provided derived expression verbatim, avoid double-wrapping
        metric_expr = literal_column(derived_expr).label("metric")
    elif mf_upper.startswith("COUNT("):
        # handle COUNT(*) or COUNT(col)
        inner = mf[mf.find("(") + 1: mf.rfind(")")].strip()
        if inner == "*" or inner == "":
            metric_expr = func.count().label("metric")
        else:
            metric_expr = func.count(text(inner)).label("metric")
    elif mf_upper.startswith("AVG("):
        inner = mf[mf.find("(") + 1: mf.rfind(")")].strip()
        metric_expr = func.avg(text(inner)).label("metric")
    elif mf_upper.startswith("SUM("):
        # already an explicit SUM expression
        metric_expr = literal_column(mf).label("metric")
    elif any(op in mf for op in ["+", "-", "*", "/"]) or "(" in mf:
        # treat as a derived expression with its own aggregation(s)
        metric_expr = literal_column(mf).label("metric")
    else:
        # plain column -> default to SUM
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

    elif strategy in ("multi_trend", "multi_group"):
        # Multi-dimensional grouping: e.g., [\"sales_rep\", \"month\"]
        # Build select columns for each group dimension
        select_cols = []
        group_exprs = []
        order_cols = []
        
        # Month expression if present
        month_expr = None
        if "month" in group_cols:
            month_expr = func.strftime("%Y-%m", literal_column(f"f.{date_column}")).label("month")
            select_cols.append(month_expr)
            group_exprs.append(month_expr)
            order_cols.append(month_expr)
        
        # Non-month dimensions
        dim_tables_needed = {}
        for col in group_cols:
            if col == "month":
                continue  # already handled
            
            # Check if dimension is in fact table
            if col in fact_cols:
                col_expr = literal_column(f"f.{col}").label(col)
                select_cols.append(col_expr)
                group_exprs.append(literal_column(f"f.{col}"))
                order_cols.append(literal_column(f"f.{col}"))
            else:
                # Find dim table for this column
                dim_table = _find_dim_table_for_column(col, schema) if schema else None
                if not dim_table and Path("enhanced_sales.db").exists():
                    with sqlite3.connect(str(Path("enhanced_sales.db"))) as conn:
                        cur = conn.cursor()
                        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'dim_%'")
                        for (t,) in cur.fetchall():
                            cur.execute(f"PRAGMA table_info('{t}')")
                            cols = [r[1] for r in cur.fetchall()]
                            if col in cols:
                                dim_table = t
                                break
                
                if dim_table:
                    # Assign alias for this dim table
                    if dim_table not in dim_tables_needed:
                        dim_tables_needed[dim_table] = {"alias": f"d{len(dim_tables_needed)}", "column": col}
                    alias = dim_tables_needed[dim_table]["alias"]
                    col_expr = literal_column(f"{alias}.{col}").label(col)
                    select_cols.append(col_expr)
                    group_exprs.append(literal_column(f"{alias}.{col}"))
                    order_cols.append(literal_column(f"{alias}.{col}"))
                else:
                    # Fallback: assume it's on fact table
                    col_expr = literal_column(f"f.{col}").label(col)
                    select_cols.append(col_expr)
                    group_exprs.append(literal_column(f"f.{col}"))
                    order_cols.append(literal_column(f"f.{col}"))
        
        # Add metric column
        select_cols.append(metric_expr)
        
        # Build FROM clause with necessary JOINs
        from_clause = f"{fact_table} f"
        join_clauses = []
        
        # Join dimension tables for group_by columns
        for dim_table, info in dim_tables_needed.items():
            join_key = _find_join_key(fact_table, dim_table, fact_cols, schema) if schema else None
            if not join_key:
                candidate = dim_table.replace('dim_', '') + '_id'
                if candidate in fact_cols:
                    join_key = candidate
            if join_key:
                join_clauses.append(f"JOIN {dim_table} {info['alias']} ON f.{join_key} = {info['alias']}.{join_key}")
        
        # Build WHERE clauses (date filter + dimension filters)
        where_clauses = [f"f.{date_column} >= :start_date", f"f.{date_column} <= :end_date"]
        dim_alias_counter = len(dim_tables_needed)
        
        for col, val in (intent.get("filters") or {}).items():
            mapped = _map_dimension(col, config) or col
            if mapped in fact_cols:
                where_clauses.append(f"f.{mapped} = :{col}")
            else:
                # Check if filter column is in one of the already-joined dim tables
                found_in_existing = False
                for dim_table, info in dim_tables_needed.items():
                    dim_cols = _get_table_columns(dim_table, schema) if schema else []
                    if mapped in dim_cols:
                        where_clauses.append(f"{info['alias']}.{mapped} = :{col}")
                        found_in_existing = True
                        break
                
                if not found_in_existing:
                    # Need to join a new dim table for this filter
                    dim_table = _find_dim_table_for_column(mapped, schema) if schema else None
                    if not dim_table and Path("enhanced_sales.db").exists():
                        with sqlite3.connect(str(Path("enhanced_sales.db"))) as conn:
                            cur = conn.cursor()
                            cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'dim_%'")
                            for (t,) in cur.fetchall():
                                cur.execute(f"PRAGMA table_info('{t}')")
                                cols = [r[1] for r in cur.fetchall()]
                                if mapped in cols:
                                    dim_table = t
                                    break
                    
                    if dim_table:
                        join_key = _find_join_key(fact_table, dim_table, fact_cols, schema) if schema else None
                        if not join_key:
                            candidate = dim_table.replace('dim_', '') + '_id'
                            if candidate in fact_cols:
                                join_key = candidate
                        if join_key:
                            falias = f"d{dim_alias_counter}"
                            dim_alias_counter += 1
                            join_clauses.append(f"JOIN {dim_table} {falias} ON f.{join_key} = {falias}.{join_key}")
                            where_clauses.append(f"{falias}.{mapped} = :{col}")
                        else:
                            where_clauses.append(f"f.{mapped} = :{col}")
                    else:
                        where_clauses.append(f"f.{mapped} = :{col}")
        
        # Build final SELECT
        full_from = " ".join([from_clause] + join_clauses)
        sel = select(*select_cols).select_from(text(full_from))
        for w in where_clauses:
            sel = sel.where(text(w))
        sel = sel.group_by(*group_exprs).order_by(*order_cols)

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

                # Build from clause with initial join for group_by dimension
                from_clause = f"{fact_table} f JOIN {dim_table} d ON f.{join_key} = d.{join_key}"
                additional_joins = []
                where_clauses = [f"f.{date_column} >= :start_date", f"f.{date_column} <= :end_date"]
                dim_alias_counter = 0
                
                # Process filters - they may live in different dim tables
                for col, val in (intent.get("filters") or {}).items():
                    mapped = _map_dimension(col, config) or col
                    if mapped in fact_cols:
                        where_clauses.append(f"f.{mapped} = :{col}")
                    elif mapped == group_col:
                        # Filter is on the same dimension we're grouping by
                        where_clauses.append(f"d.{mapped} = :{col}")
                    else:
                        # Filter lives in a different dim table - find and join it
                        filter_dim_table = _find_dim_table_for_column(mapped, schema) if schema else None
                        
                        if not filter_dim_table:
                            db_path = Path("enhanced_sales.db")
                            if db_path.exists():
                                with sqlite3.connect(str(db_path)) as conn:
                                    cur = conn.cursor()
                                    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'dim_%'")
                                    for (t,) in cur.fetchall():
                                        cur.execute(f"PRAGMA table_info('{t}')")
                                        cols = [r[1] for r in cur.fetchall()]
                                        if mapped in cols:
                                            filter_dim_table = t
                                            break
                        
                        if filter_dim_table and filter_dim_table != dim_table:
                            # Need to join another dim table for this filter
                            filter_join_key = _find_join_key(fact_table, filter_dim_table, fact_cols, schema) if schema else None
                            if not filter_join_key:
                                candidate = filter_dim_table.replace('dim_', '') + '_id'
                                if candidate in fact_cols:
                                    filter_join_key = candidate
                            if filter_join_key:
                                falias = f"d{dim_alias_counter}"
                                dim_alias_counter += 1
                                additional_joins.append(f"JOIN {filter_dim_table} {falias} ON f.{filter_join_key} = {falias}.{filter_join_key}")
                                where_clauses.append(f"{falias}.{mapped} = :{col}")
                            else:
                                where_clauses.append(f"d.{mapped} = :{col}")
                        else:
                            where_clauses.append(f"d.{mapped} = :{col}")
                
                full_from = " ".join([from_clause] + additional_joins)
                sel = select(literal_column(f"d.{group_col}").label("group_col"), metric_expr).select_from(text(full_from))
                for w in where_clauses:
                    sel = sel.where(text(w))
                sel = sel.group_by(literal_column(f"d.{group_col}")).order_by(text("metric DESC"))

    # Prepare params and bind them to the Select. Return the Select and params dict.
    params = {"start_date": start_date, "end_date": end_date}
    for col, val in (intent.get("filters") or {}).items():
        params[col] = val

    # Bind params into the Select for convenience (so callers can execute
    # the Select directly via SQLAlchemy engines or compile it with
    # literal_binds for debugging/tests).
    sel = sel.params(**params)

    # Print the generated SQL (with parameter placeholders)
    print("\n[BUILDER] Generated SQL (with placeholders):")
    print(str(sel))
    print("[BUILDER] Params:", params)

    return sel, params


def _determine_strategy(intent: Dict[str, Any]) -> str:
    """Determine SQL build strategy based on group_by structure."""
    group_by = intent.get("group_by")
    
    # Check for array group_by (multi-dimensional)
    if isinstance(group_by, list):
        if "month" in group_by:
            return "multi_trend"  # Multi-dimensional with time
        return "multi_group"  # Multi-dimensional without time
    
    # Single dimension or None
    if group_by in (None, "", "month"):
        if group_by == "month":
            return "trend"
        return "summary"
    return "group_by"


def _map_dimension(dimension: str | None, config: Dict[str, Any]) -> str:
    if not dimension:
        return ""
    return config["dimensions"].get(dimension, dimension)


__all__ = ["build_sql", "SQLBuilderError"]
