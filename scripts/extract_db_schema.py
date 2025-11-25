#!/usr/bin/env python3
"""
Extract SQLite DB schema and write JSON to config_store/tenant1_db_schema.json

This script inspects tables, columns, PRAGMA foreign_key_list and infers likely
foreign keys heuristically. Declared FKs are marked with source 'declared',
inferred ones with source 'inferred'.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Dict, Any, List

DB_PATH = Path("enhanced_sales.db")
OUT_PATH = Path("config_store") / "tenant1_db_schema.json"


def inspect_table(conn: sqlite3.Connection, table: str) -> Dict[str, Any]:
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info('{table}')")
    cols = []
    pk_cols = []
    for r in cur.fetchall():
        # r: cid, name, type, notnull, dflt_value, pk
        cid, name, typ, notnull, dflt, pk = r
        cols.append({
            "name": name,
            "type": typ,
            "notnull": bool(notnull),
            "default": dflt,
            "pk": bool(pk),
        })
        if pk:
            pk_cols.append(name)

    # declared foreign keys
    fk_list = []
    try:
        cur.execute(f"PRAGMA foreign_key_list('{table}')")
        for r in cur.fetchall():
            # id, seq, table, from, to, on_update, on_delete, match
            _id, seq, ref_table, from_col, to_col, on_upd, on_del, match = r
            fk_list.append({
                "column": from_col,
                "ref_table": ref_table,
                "ref_column": to_col,
                "on_update": on_upd,
                "on_delete": on_del,
                "match": match,
                "source": "declared",
            })
    except Exception:
        pass

    return {
        "table": table,
        "columns": cols,
        "primary_key": pk_cols,
        "declared_foreign_keys": fk_list,
    }


def infer_foreign_keys(tables_meta: Dict[str, Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Heuristically infer FKs by matching column names like <base>_id to tables named dim_<base> or <base> or similar.
    """
    inferred = []
    table_names = set(tables_meta.keys())
    for table, meta in tables_meta.items():
        for col in meta["columns"]:
            cname = col["name"]
            if not cname.endswith("_id"):
                continue
            base = cname[:-3]
            candidates = []
            # look for dim_<base>, <base>, dim_<base>s, <base>s
            candidates.extend([f"dim_{base}", base, f"dim_{base}s", f"{base}s"]) 
            found = None
            for cand in candidates:
                if cand in table_names:
                    found = cand
                    break
            if found:
                inferred.append({
                    "table": table,
                    "column": cname,
                    "ref_table": found,
                    "ref_column": cname,
                    "source": "inferred",
                })
    return inferred


def build_schema(db_path: Path) -> Dict[str, Any]:
    if not db_path.exists():
        raise SystemExit(f"DB not found at {db_path}")

    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")
    tables = [r[0] for r in cur.fetchall()]

    tables_meta: Dict[str, Dict[str, Any]] = {}
    for t in tables:
        tables_meta[t] = inspect_table(conn, t)

    inferred = infer_foreign_keys(tables_meta)

    # combine declared and inferred per table
    for inf in inferred:
        table = inf["table"]
        tables_meta[table].setdefault("inferred_foreign_keys", []).append({
            "column": inf["column"],
            "ref_table": inf["ref_table"],
            "ref_column": inf["ref_column"],
            "source": "inferred",
        })

    conn.close()

    return {
        "database": str(db_path),
        "tables": tables_meta,
    }


def main():
    schema = build_schema(DB_PATH)
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
