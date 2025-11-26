"""
LLM-backed intent parser.

This module constructs a schema-aware prompt and asks OpenAI's API to
return the structured intent JSON. It is meant to be run in an environment
with network access and `OPENAI_API_KEY` set. We still validate the LLM
output elsewhere before turning it into SQL.
"""
from __future__ import annotations

import json
import os
from textwrap import dedent
from typing import Dict, Any

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover - executed only when package missing
    raise RuntimeError(
        "openai package not installed. Run `pip install openai` in your environment."
    ) from exc


MODEL_NAME = os.getenv("OPENAI_INTENT_MODEL", "gpt-4o-mini")
def _load_db_schema_summary(schema_path: str = "config_store/tenant1_db_schema.json") -> str:
    """Load the extracted DB schema JSON (if present) and return a concise human- and machine-readable summary.

    The summary lists tables and their top columns and is intended to be embedded in prompts
    so the LLM has authoritative table/column information.
    """
    from pathlib import Path

    p = Path(schema_path)
    if not p.exists():
        return "(DB schema not available)"

    import json

    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except Exception:
        return "(DB schema unreadable)"

    parts = []
    tables = data.get("tables", {}) or {}
    for tname, meta in tables.items():
        cols = [c.get("name") for c in meta.get("columns", [])][:8]
        parts.append(f"- {tname}: {', '.join(cols)}")

    return "\n".join(parts)

SYSTEM_PROMPT = dedent(
        """
        You are a schema-aware analytics assistant that MUST output valid JSON ONLY. Follow these rules exactly.

        Output schema (single JSON object, no commentary, no fences):
        {
            "metric": string,                # one of the tenant metrics
            "filters": { <dimension>: <value>, ... },  # dimensions from tenant config
            "group_by": string|null,         # a dimension name or "month" for time trends
            "date_range": string             # one of the tenant date_ranges
        }

    Prompting rules:
    - You MUST use only metrics, dimensions and date_ranges present in the tenant config summary supplied in the user prompt.
    - If the question is fundamentally impossible to answer with available schema (e.g., asking for next/future data when only historical ranges exist), RETURN:
      {"clarification_required": true, "message": "<ask a short disambiguating question>"}
    - Do NOT invent table or column names beyond what is provided.
    - When a token clearly maps to a region (e.g., EMEA, AMER, country names), set the `region` filter.
    - Prefer exact matches to tenant dimension names; do not normalize into other dimensions unless explicit.
    - Map semantically similar terms to available options:
      * "last quarter" / "current quarter" → use closest available range (last_3_months)
      * "last year" / "past year" → use last_12_months
      * "last 2 years" → use last_24_months if available, else last_12_months
      * Ignore ranking modifiers like "Top 5", "Top 3" — just return the group_by and metric
      * "current quarter", "this quarter", "year-to-date" → map to last_3_months or last_12_months
    - If a metric is not in the available metrics list, request clarification instead of guessing.
    - If the user requests a specific aggregation modifier (like "average revenue", "median revenue", "percentile", "mode", "stddev"), request clarification explaining that each metric has a pre-defined aggregation and cannot be changed.
    - Only request clarification when the question is genuinely ambiguous or impossible with current schema.

        Few-shot examples (INPUT -> OUTPUT):
        - Input: "monthly revenue for sales rep Carlos Martinez for last 6 months"
            Output: {"metric":"revenue","filters":{"sales_rep":"Carlos Martinez"},"group_by":"month","date_range":"last_6_months"}

        - Input: "revenue from EMEA region for last year"
            Output: {"metric":"revenue","filters":{"region":"EMEA"},"group_by":null,"date_range":"last_12_months"}

        The user prompt will include a compact tenant config summary and a concise DB schema listing. Use them as authoritative.
        """
)


def _summarize_config(config: Dict[str, Any]) -> str:
    metrics = ", ".join(config.get("metrics", {}).keys()) or "None"
    dimensions = ", ".join(config.get("dimensions", {}).keys()) or "None"
    ranges = ", ".join(config.get("date_ranges", {}).keys()) or "None"
    fact = config.get("fact_table", "UNKNOWN")
    return dedent(
        f"""
        Fact table: {fact}
        Metrics: {metrics}
        Dimensions: {dimensions}
        Date ranges: {ranges}
        """
    ).strip()


def build_prompt(question: str, config: Dict[str, Any]) -> str:
    """Create the user prompt fed to the LLM."""
    config_summary = _summarize_config(config)
    schema_summary = _load_db_schema_summary()
    return dedent(
        f"""
        Tenant config:
        {config_summary}

        DB schema (top columns per table):
        {schema_summary}

        Question:
        {question}

        Respond with JSON only.
        """
    ).strip()


def parse_intent_with_llm(question: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Call OpenAI to parse the intent. Requires OPENAI_API_KEY in the environment.
    """
    if not question or not question.strip():
        raise ValueError("question must be a non-empty string")

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable is not set.")

    import re

    client = OpenAI(api_key=api_key)

    # Pre-normalize common synonyms or typos on the raw question so the LLM
    # sees canonical dimension names. Use whole-word replacements and longer
    # patterns first to avoid accidental double-replacements.
    norm_map = {
        "sales person": "sales_rep",
        "sale person": "sales_rep",
        "salesperson": "sales_rep",
        "sales-rep": "sales_rep",
        "rep": "sales_rep",
        "customer": "customer_name",
        "last year": "last 12 months",
        "past year": "last 12 months",
        "past 12 months": "last 12 months",
        "last 2 years": "last 24 months",
        "past 2 years": "last 24 months",
    }
    # sort by length descending to replace longer phrases first
    normalized = question
    for k in sorted(norm_map.keys(), key=lambda s: -len(s)):
        v = norm_map[k]
        # word-boundary replacement, case-insensitive
        normalized = re.sub(r"\b" + re.escape(k) + r"\b", v, normalized, flags=re.IGNORECASE)

    user_prompt = build_prompt(normalized, config)

    response = client.responses.create(
        model=MODEL_NAME,
        temperature=0.0,
        input=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
    )

    content = response.output[0].content[0].text  # type: ignore[attr-defined]

    # Normalize common markdown/code-fence wrappers the LLM may include.
    if isinstance(content, str):
        content = content.strip()
        # Remove ```json or ``` fences if present
        if content.startswith("```"):
            lines = content.splitlines()
            # drop opening fence
            if lines and lines[0].startswith("```"):
                lines = lines[1:]
            # drop closing fence
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # Fallback: try to extract the first JSON object block between
        # the first '{' and the last '}' in the response text.
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = content[start : end + 1]
            try:
                parsed = json.loads(snippet)
            except json.JSONDecodeError as exc:
                raise RuntimeError(f"LLM returned invalid JSON: {content}") from exc
        else:
            raise RuntimeError(f"LLM returned invalid JSON: {content}")

    if parsed.get("clarification_required"):
        raise RuntimeError(f"LLM needs clarification: {parsed.get('message')}")

    _validate_llm_response(parsed, config)

    return parsed


def _validate_llm_response(intent: Dict[str, Any], config: Dict[str, Any]) -> None:
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


__all__ = ["parse_intent_with_llm", "build_prompt"]
