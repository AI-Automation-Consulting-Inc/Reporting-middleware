from typing import Dict, Any


def validate_intent(intent: Dict[str, Any], config: Dict[str, Any]) -> None:
    """
    Validate a parsed intent dictionary against tenant `config`.

    Raises RuntimeError on invalid fields.
    """
    metrics = set(config.get("metrics", {}).keys())
    dimensions = set(config.get("dimensions", {}).keys())
    date_ranges = set(config.get("date_ranges", {}).keys())

    metric = intent.get("metric")
    if metric not in metrics:
        raise RuntimeError(f"LLM returned unsupported metric: {metric}")

    for dim in intent.get("filters", {}):
        if dim not in dimensions:
            raise RuntimeError(f"LLM returned unsupported dimension: {dim}")

    group_by = intent.get("group_by")
    if group_by and group_by not in dimensions and group_by != "month":
        raise RuntimeError(f"LLM returned unsupported group_by: {group_by}")

    date_range = intent.get("date_range")
    if date_range not in date_ranges:
        raise RuntimeError(f"LLM returned unsupported date_range: {date_range}")
