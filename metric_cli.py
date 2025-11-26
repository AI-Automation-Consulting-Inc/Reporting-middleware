from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict

from config.config_updater import add_or_update_metric
from nlp.formula_parser import parse_nl_formula, FormulaParseError


def load_schema(path: str = "config_store/tenant1_db_schema.json") -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def load_config(path: str = "config_store/tenant1.json") -> Dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {path}")
    # Use utf-8-sig to gracefully handle BOM
    return json.loads(p.read_text(encoding="utf-8-sig"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Define or update a metric from a natural-language formula.")
    parser.add_argument("formula", help="Natural language formula, e.g. 'average revenue per user'")
    parser.add_argument("--name", help="Metric key to save as, e.g. avg_revenue_per_user. Defaults from formula.")
    parser.add_argument("--config", default="config_store/tenant1.json", help="Path to tenant config JSON")
    parser.add_argument("--schema", default="config_store/tenant1_db_schema.json", help="Path to schema JSON")

    args = parser.parse_args()

    schema = load_schema(args.schema)
    cfg = load_config(args.config)

    try:
        metric_key, expr = parse_nl_formula(args.formula, schema=schema, config=cfg)
    except FormulaParseError as e:
        print(f"ERROR: {e}")
        raise SystemExit(2)

    if args.name:
        metric_key = args.name

    add_or_update_metric(metric_key, expr, path=args.config)
    print("Metric saved:")
    print(json.dumps({"metric": metric_key, "expression": expr}, indent=2))


if __name__ == "__main__":
    main()
