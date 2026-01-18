import sqlite3
from pathlib import Path
from typing import Dict, Any, Set

DB_PATH = Path("enhanced_sales.db")


def _load_country_names(conn: sqlite3.Connection) -> Set[str]:
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT country FROM dim_region WHERE country IS NOT NULL")
    return {row[0].strip().lower() for row in cur.fetchall()}


def _load_region_names(conn: sqlite3.Connection) -> Set[str]:
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT geo_cluster FROM dim_region WHERE geo_cluster IS NOT NULL")
    return {row[0].strip().lower() for row in cur.fetchall()}


def _load_customer_names(conn: sqlite3.Connection) -> Set[str]:
    cur = conn.cursor()
    cur.execute("SELECT customer_name FROM dim_customer WHERE customer_name IS NOT NULL")
    return {row[0].strip().lower() for row in cur.fetchall()}


def disambiguate_filters(intent: Dict[str, Any], db_path: str | Path = DB_PATH) -> Dict[str, Any]:
    """Given an intent dict, adjust filters so country/region/customer values are properly categorized.

    Returns the modified intent (mutates input as well).
    """
    if not Path(db_path).exists():
        # DB not available; no-op
        return intent

    conn = sqlite3.connect(str(db_path))
    try:
        countries = _load_country_names(conn)
        regions = _load_region_names(conn)
        customers = _load_customer_names(conn)
    finally:
        conn.close()

    filters = intent.get("filters", {}) or {}

    # Normalize filter values to plain strings for matching
    for key in list(filters.keys()):
        val = filters.get(key)
        if not isinstance(val, str):
            continue
        v = val.strip().lower()
        
        # Exact match customer name -> prefer customer
        if v in customers:
            # ensure it's set on customer_name
            if key != "customer_name":
                # move value to customer_name
                filters.pop(key, None)
                filters["customer_name"] = val
            continue
            
        # Exact match country name -> set to country
        if v in countries:
            if key != "country":
                filters.pop(key, None)
                filters["country"] = val
            continue
            
        # Exact match region (geo_cluster) name -> set to region
        if v in regions:
            if key != "region":
                filters.pop(key, None)
                filters["region"] = val
            continue

    intent["filters"] = filters
    return intent
