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
            "date_range": string,            # one of the tenant date_ranges
            "derived_expression": string|null  # optional SQL expression for calculated metrics like "average X per Y"
        }

    CRITICAL RULES - NO EXCEPTIONS:
    - You MUST ONLY use metrics, dimensions, and date_ranges that are explicitly listed in the tenant config.
    - NEVER create or invent metric names, dimension names, or filter values that are not in the config.
    - If a user mentions a value not in the config (e.g., a person name, region, or product), you MUST request clarification.
    - DO NOT make assumptions about filter values - if unsure, ask for clarification.
    - If the question is ambiguous or impossible to answer with available schema, RETURN structured clarification:
      {
        "clarification_required": true,
        "interpretation": "<Your interpretation of what the user is asking>",
        "question": "<A clear yes/no question asking if your interpretation is correct>"
      }
      Example: {"clarification_required": true, "interpretation": "Total revenue divided by number of products, grouped by regions (EMEA, AMER, APAC)", "question": "Is this correct?"}
    - IMPORTANT: If the user's question includes "Clarification: yes" or similar confirmation, this means they agreed with your interpretation.
      In this case, RETURN THE ACTUAL INTENT JSON (not another clarification request).
      Extract the confirmed interpretation and convert it to proper intent JSON with metric, filters, group_by, date_range.
    - Do NOT invent table or column names beyond what is provided.
    - IMPORTANT: Distinguish between country and region:
      * Use `country` filter for specific countries (Canada, Germany, United States, etc.)
      * Use `region` filter for geographic clusters (EMEA, AMER, APAC)
    - Prefer exact matches to tenant dimension names; do not normalize into other dimensions unless explicit.
    - Map semantically similar terms to available options:
    * "last month" → use last_month (previous calendar month)
    * "this month" / "current month" → use this_month (current calendar month) if available
    * "last quarter" / "current quarter" → use closest available range (last_3_months)
    * "last year" / "past year" → use last_12_months
      * "last 2 years" → use last_24_months if available, else last_12_months
      * "current quarter", "this quarter", "year-to-date" → map to last_3_months or last_12_months
    - IGNORE ranking/limit modifiers like "Top 5", "Top 3", "bottom 10" - just return the group_by and metric WITHOUT any limit field
    - For queries like "top N <dimension> from <region>", set:
      * filters: {"region": "<region_value>"}
      * group_by: "<dimension>" (e.g., "sales_rep" for "top sales people")
      * Do NOT add a limit or top_n field
    - For "average X per Y" queries (e.g., "average revenue per product by region"):
      * Set group_by to the grouping dimension (e.g., "region")
      * Add derived_expression: "SUM(f.<metric_column>) / NULLIF(COUNT(DISTINCT f.<per_dimension_id>), 0)"
      * CRITICAL: Use the actual fact table column name from the tenant config for the metric (e.g., "net_revenue" for revenue metric, NOT "revenue")
      * Use fact table alias "f." and the ID column for the "per" dimension (e.g., product_id, customer_id, sales_rep_id)
      * Example: "average revenue per product by region" → derived_expression: "SUM(f.net_revenue) / NULLIF(COUNT(DISTINCT f.product_id), 0)", group_by: "region"
      * Example: "average ARR per customer by industry" → derived_expression: "SUM(f.arr) / NULLIF(COUNT(DISTINCT f.customer_id), 0)", group_by: "industry"
    - CRITICAL: For "average X per Y" queries WITHOUT a grouping dimension (e.g., "average deals per sales person" with no "by region"):
      * Set group_by to NULL (not the "per" dimension)
      * The derived expression counts across ALL records to get the total average
      * SPECIAL CASE: If the metric is deal_count (which is COUNT(*), not a column), use "COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT f.<per_dimension_id>), 0)"
      * Example: "average deals per sales person" → {"metric":"deal_count","filters":{},"group_by":null,"date_range":"last_3_months","derived_expression":"COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT f.sales_rep_id), 0)"}
      * Example: "average revenue per product" → {"metric":"revenue","filters":{},"group_by":null,"date_range":"last_3_months","derived_expression":"SUM(f.net_revenue) / NULLIF(COUNT(DISTINCT f.product_id), 0)"}
      * Do NOT set group_by to the "per" dimension - that would give a meaningless result (each group has exactly 1 of that dimension)
    - If a metric is not in the available metrics list, request clarification instead of guessing.
    - If the user requests a specific aggregation modifier (like "average revenue", "median revenue", "percentile", "mode", "stddev"), request clarification explaining that each metric has a pre-defined aggregation and cannot be changed.
    - Only request clarification when the question is genuinely ambiguous or impossible with current schema.

        Few-shot examples (INPUT -> OUTPUT):
        - Input: "monthly revenue for sales rep Carlos Martinez for last 6 months"
            Output: {"metric":"revenue","filters":{"sales_rep":"Carlos Martinez"},"group_by":"month","date_range":"last_6_months"}

        - Input: "revenue from EMEA region for last year"
            Output: {"metric":"revenue","filters":{"region":"EMEA"},"group_by":null,"date_range":"last_12_months"}
        
        - Input: "top 3 sales person from EMEA region"
            Output: {"metric":"revenue","filters":{"region":"EMEA"},"group_by":"sales_rep","date_range":"last_3_months"}
        
        - Input: "top performing products in United States"
            Output: {"metric":"revenue","filters":{"region":"United States"},"group_by":"product_name","date_range":"last_3_months"}
        
        - Input: "average revenue per product for all regions"
            Output: {"clarification_required":true,"interpretation":"Total revenue divided by total number of products, grouped by region (EMEA, AMER, APAC) - showing average revenue per product for each region","question":"Is this correct?"}
        
        - Input: "median deal size by customer tier"
            Output: {"clarification_required":true,"interpretation":"The 'revenue' metric (which calculates total revenue, not median) grouped by customer tier","question":"Do you want total revenue by customer tier?"}
        
        - Input: "average revenue per product for all regions\nClarification: yes, that interpretation is correct"
            Output: {"metric":"revenue","filters":{},"group_by":"region","date_range":"last_3_months","derived_expression":"SUM(f.net_revenue) / NULLIF(COUNT(DISTINCT f.product_id), 0)"}
        
        - Input: "average deals per sales person"
            Output: {"clarification_required":true,"interpretation":"Total deal count divided by the number of sales representatives, without grouping by any dimension.","question":"Is this correct?"}
        
        - Input: "average deals per sales person\nClarification: yes, that interpretation is correct"
            Output: {"metric":"deal_count","filters":{},"group_by":null,"date_range":"last_3_months","derived_expression":"COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT f.sales_rep_id), 0)"}

        The user prompt will include a compact tenant config summary and a concise DB schema listing. Use them as authoritative.
        """
)


def _summarize_config(config: Dict[str, Any]) -> str:
    metrics_dict = config.get("metrics", {})
    metrics = ", ".join(metrics_dict.keys()) or "None"
    dimensions = ", ".join(config.get("dimensions", {}).keys()) or "None"
    ranges = ", ".join(config.get("date_ranges", {}).keys()) or "None"
    fact = config.get("fact_table", "UNKNOWN")
    
    # Add metric-to-column mappings for derived expressions
    metric_mappings = []
    for metric_name, metric_expr in metrics_dict.items():
        if not isinstance(metric_expr, str):
            continue
        # Extract simple column references (non-aggregated)
        if "(" not in metric_expr and ")" not in metric_expr:
            metric_mappings.append(f"{metric_name}→{metric_expr}")
    
    mappings_str = ""
    if metric_mappings:
        mappings_str = f"\nMetric column mappings: {', '.join(metric_mappings[:5])}"  # Show first 5
    
    return dedent(
        f"""
        Fact table: {fact}
        Metrics: {metrics}
        Dimensions: {dimensions}
        Date ranges: {ranges}{mappings_str}
        """
    ).strip()


def build_prompt(question: str, config: Dict[str, Any]) -> str:
    """Create the user prompt fed to the LLM."""
    config_summary = _summarize_config(config)
    schema_summary = _load_db_schema_summary()
    # Load shared and tenant-specific rule books to give the model authoritative mapping guidance
    from pathlib import Path
    rules_general = ""
    rules_tenant = ""
    try:
        rg_path = Path("config_store/schema_rules.md")
        if rg_path.exists():
            rules_general = rg_path.read_text(encoding="utf-8")
    except Exception:
        pass
    try:
        rt_path = Path("config_store/schema_rules_tenant1.md")
        if rt_path.exists():
            rules_tenant = rt_path.read_text(encoding="utf-8")
    except Exception:
        pass

    return dedent(
        f"""
        Tenant config:
        {config_summary}

        DB schema (top columns per table):
        {schema_summary}

        === GLOBAL SCHEMA RULES ===
        {rules_general}

        === TENANT-SPECIFIC RULES ===
        {rules_tenant}

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
        # Encourage date range tokenization for the model
        "last month": "last_month",
        "previous month": "last_month",
        "this month": "this_month",
        "current month": "this_month",
    }
    # sort by length descending to replace longer phrases first
    normalized = question
    for k in sorted(norm_map.keys(), key=lambda s: -len(s)):
        v = norm_map[k]
        # word-boundary replacement, case-insensitive
        normalized = re.sub(r"\b" + re.escape(k) + r"\b", v, normalized, flags=re.IGNORECASE)

    user_prompt = build_prompt(normalized, config)

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role":"system", "content": SYSTEM_PROMPT}, {"role": "user", "content": user_prompt}],
        max_tokens=800,
        temperature=0.2,
        response_format={"type": "json_object"}
    )

    content = response.choices[0].message.content

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
        # Return the structured clarification instead of raising error
        return parsed

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
