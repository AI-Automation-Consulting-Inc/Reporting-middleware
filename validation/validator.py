"""
Intent validation against tenant config.

Checks:
- Metric exists
- Dimensions in filters/group_by exist
- Date range can be resolved
"""
from __future__ import annotations

from typing import Dict

from .date_resolver import resolve_date_range, DateResolutionError


class IntentValidationError(ValueError):
    """Raised when the intent fails validation."""


def validate_intent(intent: Dict, config: Dict) -> Dict:
    if "metric" not in intent:
        raise IntentValidationError("Intent missing metric.")

    metric = intent["metric"]
    metrics = config.get("metrics", {})
    if metric not in metrics:
        raise IntentValidationError(f"Unsupported metric: {metric}")

    dimensions = config.get("dimensions", {})
    filters = intent.get("filters", {})
    for key in filters:
        if key not in dimensions:
            raise IntentValidationError(f"Unsupported dimension filter: {key}")

    group_by = intent.get("group_by")
    if group_by and group_by not in dimensions and group_by != "month":
        raise IntentValidationError(f"Unsupported group_by: {group_by}")

    try:
        start, end = resolve_date_range(intent, config)
    except DateResolutionError as exc:
        raise IntentValidationError(str(exc)) from exc

    validated = intent.copy()
    validated["resolved_dates"] = {"start_date": start, "end_date": end}
    return validated


__all__ = ["validate_intent", "IntentValidationError"]
