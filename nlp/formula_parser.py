from __future__ import annotations

import re
from typing import Dict, Optional, Tuple
import os


class FormulaParseError(ValueError):
    pass


def _slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "custom_metric"


def parse_nl_formula(nl: str, schema: Dict, config: Dict) -> Tuple[str, str]:
    """
    Parse a natural-language metric formula into a SQL expression string suitable for the
    metrics map in tenant config. Returns (metric_key, sql_expression).

    Supported patterns (rule-based, conservative):
    - "total revenue" / "revenue" -> SUM(net_revenue)
    - "deal count" / "number of deals" -> COUNT(*)
    - "number of customers|users|accounts" -> COUNT(DISTINCT customer_id)
    - "<X> per <Y>" -> SUM(X_col) / NULLIF(COUNT(DISTINCT Y_id), 0)
    - "average <X> per <Y>" -> SUM(X_col) / NULLIF(COUNT(DISTINCT Y_id), 0)

    Notes:
    - X supports revenue|arr|acv|gross margin
    - Y supports customer|user|account
    - Uses fact table columns only to avoid requiring extra joins for metric expr
    """

    nl_clean = nl.strip().lower()
    # Normalize common filler words and typos to improve matching
    replacements = {
        "  ": " ",
        " of all customers": "",
        " of all customer": "",
        " of customers": "",
        " of customer": "",
        " of all users": "",
        " of users": "",
        " of all accounts": "",
        " of accounts": "",
        " total ": " ",
        "totals ": "",
        "avg ": "average ",
        " divid by ": " divided by ",  # common typo
        " divide by ": " divided by ",
        "  ": " ",
    }
    for k, v in replacements.items():
        nl_clean = nl_clean.replace(k, v)
    nl_clean = nl_clean.strip()

    fact_table = config.get("fact_table", "fact_sales_pipeline")
    tables = (schema or {}).get("tables", {})
    fact_cols = {c["name"] for c in tables.get(fact_table, {}).get("columns", [])}

    # Column map for base metrics (with canonical synonym mapping)
    canonical_to_column = {
        "revenue": "net_revenue",
        "arr": "arr",
        "acv": "acv",
        "gross_margin": "gross_margin",
    }
    synonym_to_canonical = {
        # revenue synonyms
        "revenue": "revenue",
        "total revenue": "revenue",
        "net revenue": "revenue",
        "sales": "revenue",
        "turnover": "revenue",
        # ARR/ACV
        "arr": "arr",
        "annual recurring revenue": "arr",
        "recurring revenue": "arr",
        "acv": "acv",
        "contract value": "acv",
        "annual contract value": "acv",
        # gross margin synonyms
        "gross margin": "gross_margin",
        "gross profit": "gross_margin",
        "profit": "gross_margin",
        "gm": "gross_margin",
    }

    # Entity id columns (fact-level) for distinct counts
    entity_ids = {
        "customer": "customer_id",
        "customers": "customer_id",
        "user": "customer_id",
        "users": "customer_id",
        "account": "customer_id",
        "accounts": "customer_id",
        "company": "customer_id",
        "companies": "customer_id",
        "logo": "customer_id",
        "logos": "customer_id",
        "deal": None,  # COUNT(*) denominator
        "deals": None,
    }

    def ensure_col(col: str) -> str:
        if col not in fact_cols:
            raise FormulaParseError(f"Column '{col}' not found in fact table '{fact_table}'.")
        return col

    # 1) Direct totals
    if nl_clean in ("revenue", "total revenue", "net revenue", "sales", "turnover"):
        return _slugify("revenue"), "SUM(net_revenue)"
    if nl_clean in ("deal count", "number of deals", "count deals", "deals count"):
        return _slugify("deal_count"), "COUNT(*)"
    if nl_clean in ("number of users", "number of customers", "number of accounts"):
        cid = ensure_col(entity_ids["customer"])
        return _slugify("customers_count"), f"COUNT(DISTINCT {cid})"

    # 2) X per Y patterns (with or without 'average')
    # e.g. "average revenue per user", "revenue per customer"
    m = re.match(r"^(average\s+)?([a-z\s]+?)\s+per\s+([a-z\s]+)$", nl_clean)
    if m:
        _avg_prefix, x_raw, y_raw = m.groups()
        x = x_raw.strip()
        y = y_raw.strip()

        # map X to canonical name and base column
        canonical_x = synonym_to_canonical.get(x) or synonym_to_canonical.get(x.replace(" ", ""))
        if not canonical_x:
            raise FormulaParseError(f"Unsupported numerator '{x}'. Try revenue, arr, acv, gross margin.")
        x_col = canonical_to_column[canonical_x]

        # map Y to an entity id
        # strip leading 'count of', 'total count of', 'number of', etc.
        y = re.sub(r"^(?:total\s+)?(?:count|number)\s+of\s+", "", y)
        # detect entity anywhere in the phrase (handles 'total count of customers')
        if "customer" in y:
            y_key = "customer"
        elif "user" in y:
            y_key = "user"
        elif "account" in y:
            y_key = "account"
        elif ("count" in y or "number" in y) and "customer_id" in fact_cols:
            # Default to customers when count is mentioned without an explicit entity
            y_key = "customer"
        else:
            y_key = y.split()[0].rstrip("s")  # fallback first token
        y_id = entity_ids.get(y_key)
        # denominator expression: COUNT(*) for deal(s), else COUNT(DISTINCT id)
        if y_id is None:
            denom_expr = "COUNT(*)"
        else:
            y_id = ensure_col(y_id)
            denom_expr = f"COUNT(DISTINCT {y_id})"

        expr = f"SUM({x_col}) / NULLIF({denom_expr}, 0)"
        metric_key = _slugify(f"{canonical_x}_per_{y_key}")
        return metric_key, expr

    # Support slash form: "X / Y"
    m2a = re.match(r"^([a-z\s]+?)\s*/\s*([a-z\s]+?)$", nl_clean)
    if m2a:
        left, right = m2a.groups()
        return parse_nl_formula(f"{left} divided by {right}", schema, config)

    # Fallback for "X divided by Y" (tolerate typos like 'divide by'/'divid by')
    m2 = re.match(r"^([a-z\s]+?)\s+divid(?:e|ed)?\s+by\s+([a-z\s]+?)$", nl_clean)
    if m2:
        left, right = m2.groups()
        # reuse the 'X per Y' logic by translating
        return parse_nl_formula(f"{left} per {right}", schema, config)

    # LLM fallback: attempt to translate the NL formula into a safe SQL expr
    expr = _try_llm_formula(nl, schema=schema, config=config)
    if expr:
        # Heuristic key from NL
        metric_key = _slugify(nl)
        return metric_key, expr

    raise FormulaParseError("Could not parse formula. Supported examples: 'revenue per customer', 'average revenue per user', 'number of customers'.")


def _try_llm_formula(nl: str, schema: Dict, config: Dict) -> Optional[str]:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    try:
        from openai import OpenAI  # type: ignore
    except Exception:
        return None

    # Build guardrails: only allow fact-table columns and limited aggregations
    fact_table = config.get("fact_table", "fact_sales_pipeline")
    tables = (schema or {}).get("tables", {})
    fact_cols = [c.get("name") for c in tables.get(fact_table, {}).get("columns", [])]
    allowed_cols = ", ".join(sorted(set([c for c in fact_cols if c]))) or "net_revenue, customer_id, arr, acv, gross_margin"

    system = (
        "You translate a user's metric formula into a single SQL expression using ONLY the fact table columns. "
        "Return JSON ONLY with `{\"expression\": <SQL>}`. \n"
        "Constraints: use only these columns: "
        + allowed_cols
        + ". Allowed aggregates: SUM, AVG, COUNT, COUNT(DISTINCT ...). "
        "Prefer: SUM(net_revenue) for total revenue; COUNT(DISTINCT customer_id) for number of customers. "
        "If numerator/denominator present, use NULLIF(den,0) to avoid divide-by-zero. No table qualifiers, just columns."
    )

    user = f"Natural language formula: {nl}\nReturn JSON with the SQL expression only."

    model = os.getenv("OPENAI_INTENT_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=api_key)
    resp = client.responses.create(
        model=model,
        temperature=0,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    content = resp.output[0].content[0].text  # type: ignore[attr-defined]
    if not isinstance(content, str):
        return None
    content = content.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    try:
        data = json.loads(content)
        expr = data.get("expression")
        if isinstance(expr, str) and expr:
            return expr
    except Exception:
        return None
    return None
