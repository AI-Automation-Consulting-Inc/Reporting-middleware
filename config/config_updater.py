from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


class ConfigUpdateError(ValueError):
    pass


def load_config(path: str = "config_store/tenant1.json") -> Dict:
    p = Path(path)
    if not p.exists():
        raise ConfigUpdateError(f"Config file not found: {path}")
    return json.loads(p.read_text(encoding="utf-8-sig"))


def save_config(cfg: Dict, path: str = "config_store/tenant1.json") -> None:
    p = Path(path)
    p.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def add_or_update_metric(metric_key: str, sql_expression: str, path: str = "config_store/tenant1.json") -> None:
    cfg = load_config(path)
    metrics = cfg.setdefault("metrics", {})
    metrics[metric_key] = sql_expression
    save_config(cfg, path)
