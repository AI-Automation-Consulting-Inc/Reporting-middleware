"""
Simple heuristic-based intent parser used for the MVP.

The parser inspects the natural-language question and derives a structured
intent dictionary with the keys described in the PRD:

{
    "metric": str,
    "filters": Dict[str, str],
    "group_by": Optional[str],
    "date_range": str
}

It is purposely deterministic: we rely on explicit keyword maps rather than
LLM output so we can guarantee consistent SQL generation downstream.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple


DEFAULT_METRIC = "revenue"
DEFAULT_DATE_RANGE = "last_12_months"

METRIC_SYNONYMS: Dict[str, List[str]] = {
    "revenue": ["revenue", "sales", "turnover", "booking"],
    "arr": ["arr", "annual recurring revenue", "recurring revenue"],
    "acv": ["acv", "contract value", "annual contract value"],
    "gross_margin": ["margin", "gross margin"],
    "avg_discount": ["discount", "discount rate"],
    "pipeline_value": ["pipeline", "pipeline value", "open pipeline"],
    "deal_count": ["deal count", "number of deals", "deals"],
}

DATE_RANGE_KEYWORDS: Dict[str, List[str]] = {
    "last_12_months": ["last 12 months", "past year", "last year"],
    "last_6_months": ["last 6 months", "past 6 months", "last half"],
    "last_3_months": ["last 3 months", "past quarter", "last quarter"],
}

DIMENSION_VALUE_PATTERNS: Dict[str, List[str]] = {
    "customer_name": [
        r"customer(?:\s+named)?\s+(?P<value>[A-Z][\w\s&]+?)(?=(?:\s+for|\s+in|\s+during|\s+over|$))",
        r"from\s+(?P<value>[A-Z][\w\s&]+?)(?=(?:\s+for|\s+in|\s+during|\s+over|$))",
    ],
    "product_name": [
        r"product\s+(?P<value>[A-Z][\w\s&]+?)(?=(?:\s+for|\s+in|\s+during|\s+over|$))",
        # avoid capturing temporal phrases like 'last 6 months' as a product
        r"for\s+(?P<value>(?!last\b|past\b|\d)[A-Z][\w\s&]+?)(?=(?:\s+in|\s+during|\s+over|\s+last|$))",
        r"(?<=for\s)(?P<value>[A-Z][\w\s&]+)(?=\s+generated)",
    ],
    "region": [
        r"from\s+(?P<value>(?:EMEA|AMER|APAC|Europe|Asia|North America|[A-Z][\w\s&]+?))(?=(?:\s+region|\s+for|\s+during|\s+over|\s+last|$))",
        r"in\s+(?P<value>[A-Z][\w\s&]+?)(?=(?:\s+region|\s+for|\s+during|\s+over|\s+last|$))",
        r"region\s+(?P<value>[A-Z][\w\s&]+?)(?=(?:\s+for|\s+during|\s+over|\s+last|$))",
        r"for\s+(?P<value>(?:EMEA|AMER|APAC|Europe|Asia|North America))(?=(?:\s+generated|\s+by|\s+during|\s+over|\s+last|$))",
    ],
    "pipeline_stage": [
        r"stage\s+(?P<value>[A-Za-z ]+)",
        r"pipeline\s+(?P<value>[A-Za-z ]+)",
    ],
    "sales_rep": [
        r"rep\s+(?P<value>[A-Z][\w\s&]+?)(?=(?:\s+in|\s+for|\s+with|\s+who|\s+that|\s+which|$))",
        r"by\s+rep\s+(?P<value>[A-Z][\w\s&]+?)(?=(?:\s+in|\s+for|\s+with|\s+who|\s+that|\s+which|$))",
        r"by\s+(?P<value>[A-Z][\w\s&]+?)(?=(?:\s+in|\s+for|\s+with|\s+who|\s+that|\s+which|$))",
    ],
    "channel": [
        r"channel\s+(?P<value>[A-Za-z ]+)",
        r"via\s+(?P<value>[A-Za-z ]+)",
    ],
}

DISCARD_FILTER_VALUES = {"the", "last", "past", "month", "months", "year", "years"}
REGION_NORMALIZATION = {
    "emea": "EMEA",
    "amer": "AMER",
    "apac": "APAC",
    "europe": "EMEA",
    "asia": "APAC",
    "north america": "AMER",
}
REGION_TOKENS = {
    token.upper()
    for token in list(REGION_NORMALIZATION.keys()) + list(REGION_NORMALIZATION.values())
}

STATUS_KEYWORDS = {
    "deal_status": {
        "closed_won": ["closed won", "won deals"],
        "closed_lost": ["closed lost", "lost deals"],
        "open": ["open pipeline", "open deals", "pipeline only"],
        "returned": ["returned", "refund"],
    },
    "contract_type": {
        "renewal": ["renewal", "renewals"],
        "expansion": ["expansion", "upsell"],
        "new": ["new business", "new logos", "new deals"],
    },
}

GROUP_BY_KEYWORDS = {
    "month": ["trend", "monthly", "over time", "per month"],
}

GROUP_BY_DIMENSION_KEYWORDS = {
    "region": ["region", "country", "geo"],
    "product_name": ["product", "sku"],
    "industry": ["industry", "sector"],
    "customer_tier": ["tier", "segment"],
    "channel": ["channel"],
    "pipeline_stage": ["stage"],
    "sales_rep": ["rep", "sales rep"],
}


def parse_intent(question: str, config: Dict) -> Dict:
    """
    Parse the natural-language question into structured intent.

    Parameters
    ----------
    question:
        User's natural-language analytics question.
    config:
        Tenant semantic model (subset of tenant1.json) containing metrics,
        dimensions, and supported date ranges.

    Raises
    ------
    IntentClarificationRequired
        When no explicit metric or date range can be inferred and the tenant
        supports multiple options, prompting the caller to ask the user for
        clarification before running SQL.
    """
    if not question or not question.strip():
        raise ValueError("question must be a non-empty string")

    normalized = question.strip()
    lower = normalized.lower()

    metric, metric_confident = _detect_metric(lower, config)
    date_range, date_confident = _detect_date_range(lower, config)
    filters = _detect_filters(normalized)
    group_by = _detect_group_by(lower)
    explicit_metric = _has_explicit_metric(lower, metric)
    metric = _maybe_switch_metric_for_listing(
        metric, explicit_metric, lower, group_by, config
    )

    if not metric_confident:
        raise IntentClarificationRequired(
            "Please specify which metric you care about (e.g., revenue, ARR, pipeline value)."
        )

    if not date_confident:
        raise IntentClarificationRequired(
            "Please clarify the date range (e.g., last 12 months, last 6 months)."
        )

    return {
        "metric": metric,
        "filters": filters,
        "group_by": group_by,
        "date_range": date_range,
    }


def _detect_metric(question_lower: str, config: Dict) -> Tuple[str, bool]:
    configured_metrics = config.get("metrics", {})
    for metric_key, synonyms in METRIC_SYNONYMS.items():
        if metric_key not in configured_metrics:
            continue
        for synonym in synonyms:
            if synonym in question_lower:
                return metric_key, True

    metrics = list(configured_metrics.keys())
    if not metrics:
        return DEFAULT_METRIC, True

    default_metric = (
        DEFAULT_METRIC if DEFAULT_METRIC in configured_metrics else metrics[0]
    )

    unsupported_reference = False
    for metric_key, synonyms in METRIC_SYNONYMS.items():
        if metric_key in configured_metrics:
            continue
        if any(synonym in question_lower for synonym in synonyms):
            unsupported_reference = True
            break

    return default_metric, not unsupported_reference


def _detect_date_range(question_lower: str, config: Dict) -> Tuple[str, bool]:
    allowed = set(config.get("date_ranges", {}).keys())
    for range_key, keywords in DATE_RANGE_KEYWORDS.items():
        if range_key not in allowed:
            continue
        for keyword in keywords:
            if keyword in question_lower:
                return range_key, True

    if not allowed:
        return DEFAULT_DATE_RANGE, True

    default_range = (
        DEFAULT_DATE_RANGE if DEFAULT_DATE_RANGE in allowed else next(iter(allowed))
    )
    date_tokens_present = bool(
        re.search(
            r"\b(last|past|this|month|months|quarter|year|years|week|weeks|today|yesterday|ytd|mtd)\b",
            question_lower,
        )
    )
    confident = len(allowed) == 1 or not date_tokens_present
    return default_range, confident


def _detect_filters(question: str) -> Dict[str, str]:
    filters: Dict[str, str] = {}
    for dimension, patterns in DIMENSION_VALUE_PATTERNS.items():
        value = _first_match(question, patterns, dimension)
        if value:
            filters[dimension] = value

    lowered = question.lower()
    for dimension, mapping in STATUS_KEYWORDS.items():
        for value, keywords in mapping.items():
            if any(keyword in lowered for keyword in keywords):
                filters[dimension] = value
                break

    return filters


def _detect_group_by(question_lower: str) -> Optional[str]:
    for group_key, keywords in GROUP_BY_KEYWORDS.items():
        if any(keyword in question_lower for keyword in keywords):
            return group_key

    if "sales person" in question_lower or "salespeople" in question_lower:
        return "sales_rep"

    match = re.search(r"\bby\s+([a-z ]+)", question_lower)
    if match:
        token = match.group(1).strip()
        for dimension, keywords in GROUP_BY_DIMENSION_KEYWORDS.items():
            if any(token.startswith(keyword) for keyword in keywords):
                return dimension

    if any(word in question_lower for word in ("highest", "top", "best", "most")):
        if "rep" in question_lower or "sales rep" in question_lower:
            return "sales_rep"
        if "region" in question_lower or "geo" in question_lower:
            return "region"
        if "product" in question_lower:
            return "product_name"
        if "channel" in question_lower:
            return "channel"

    return None


def _first_match(question: str, patterns: List[str], dimension: str) -> Optional[str]:
    for pattern in patterns:
        match = re.search(pattern, question, flags=re.IGNORECASE)
        if match:
            raw = match.group("value").strip().strip(",.")
            normalized = _normalize_value(raw)
            if normalized.lower() in DISCARD_FILTER_VALUES:
                continue
            processed = _post_process_value(dimension, normalized, match.group("value"))
            if processed:
                return processed
    return None


def _normalize_value(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _post_process_value(dimension: str, value: str, raw_value: str) -> Optional[str]:
    lowered = value.lower()
    if dimension == "region":
        cleaned = lowered.replace(" region", "").strip()
        canonical = REGION_NORMALIZATION.get(cleaned, cleaned.upper())
        return canonical

    if dimension == "sales_rep":
        if not any(char.isupper() for char in raw_value):
            return None
        return value

    if dimension == "product_name":
        cleaned = re.sub(r"\bgenerated\b", "", lowered)
        cleaned = re.sub(r"\s+by\s+.*$", "", cleaned).strip()
        if cleaned.upper() in REGION_TOKENS:
            return None
        return cleaned.title()

    return value


def _has_explicit_metric(question_lower: str, metric: str) -> bool:
    if metric == "revenue" and _mentions_sales_person(question_lower):
        return False
    synonyms = METRIC_SYNONYMS.get(metric, [])
    return any(synonym in question_lower for synonym in synonyms)


def _maybe_switch_metric_for_listing(
    metric: str,
    explicit_metric: bool,
    question_lower: str,
    group_by: Optional[str],
    config: Dict,
) -> str:
    if explicit_metric:
        return metric

    metrics = config.get("metrics", {})
    listing_triggers = ("list", "show all", "which", "who")
    if any(trigger in question_lower for trigger in listing_triggers):
        if "deal_count" in metrics:
            return "deal_count"

    if group_by and group_by != "month":
        if "count" in question_lower and "deal_count" in metrics:
            return "deal_count"

    return metric


def _mentions_sales_person(question_lower: str) -> bool:
    return any(
        token in question_lower for token in ("sales person", "salespeople", "sales persons")
    )


__all__ = ["parse_intent", "IntentClarificationRequired"]
class IntentClarificationRequired(Exception):
    """Raised when the parser cannot confidently build an intent."""

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)
