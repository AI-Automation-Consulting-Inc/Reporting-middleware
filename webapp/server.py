from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Dict, Any, List

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles


app = FastAPI(title="Reporting Middleware UI API")


def _load_config() -> Dict[str, Any]:
    return json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))


def _load_validator():
    try:
        from validation.validator import validate_intent, IntentValidationError  # type: ignore

        return validate_intent, IntentValidationError
    except Exception:
        try:
            from nlp.validator import validate_intent, IntentValidationError  # type: ignore

            return validate_intent, IntentValidationError
        except Exception:
            from nlp.validator import validate_intent as _validate_intent  # type: ignore

            def validate_intent(intent, config):
                _validate_intent(intent, config)
                return {**intent, "resolved_dates": {"date_range": intent.get("date_range")}}

            class IntentValidationError(RuntimeError):
                pass

            return validate_intent, IntentValidationError


@app.post("/api/query")
def api_query(payload: Dict[str, Any]):
    question: str = (payload.get("question") or "").strip()
    clarification: Optional[str] = (payload.get("clarification") or None)
    if not question:
        return JSONResponse({"error": "question is required"}, status_code=400)

    # Combine clarification inline to guide the model without complex session state
    if clarification:
        question = f"{question}\nClarification: {clarification.strip()}"

    config = _load_config()
    validate_intent, IntentValidationError = _load_validator()

    # Parse intent via LLM
    # Detect common modifiers/denominators to build ephemeral expressions
    lowered_q = question.lower()
    ephemeral_expr: Optional[str] = None
    # Average revenue per sales person
    if ("average" in lowered_q or "avg" in lowered_q) and "revenue" in lowered_q and ("sales person" in lowered_q or "sales_rep" in lowered_q or "salesperson" in lowered_q):
        # Qualify columns to fact table alias used by builder (f.)
        ephemeral_expr = "SUM(f.net_revenue) / NULLIF(COUNT(DISTINCT f.rep_name), 0)"

    try:
        from nlp.llm_intent_parser import parse_intent_with_llm  # type: ignore

        intent = parse_intent_with_llm(question, config)
        parser_used = "llm"
        if ephemeral_expr:
            intent["derived_expression"] = ephemeral_expr
            intent["metric"] = intent.get("metric", "revenue")
    except RuntimeError as exc:
        msg = str(exc)
        # If LLM asks for clarification and the client did provide one, attempt a heuristic fallback
        if msg.lower().startswith("llm needs clarification:"):
            if clarification:
                # Very lightweight heuristic: map common phrases to a valid intent without modifiers
                lowered = (question or "").lower()
                metric = "revenue" if "revenue" in lowered else next(iter(config.get("metrics", {}).keys()), "revenue")
                group_by = None
                if "sales person" in lowered or "sales_rep" in lowered or "sales person" in (clarification or "").lower():
                    group_by = "sales_rep" if "sales_rep" in (config.get("dimensions") or {}) else None
                if "region" in lowered or "emea" in lowered or "amer" in lowered or "apac" in lowered:
                    group_by = "region"
                # Prefer month trend if explicitly asked
                if "monthly" in lowered or "month" in lowered:
                    group_by = "month"
                # Default range: last_3_months if not present
                date_range = "last_3_months"
                # If config supports last_month/this_month, pick last_6_months for broader view when asking averages
                if "last month" in lowered:
                    date_range = "last_month"
                elif "last 6 months" in lowered:
                    date_range = "last_6_months"
                elif "last 12 months" in lowered or "last year" in lowered:
                    date_range = "last_12_months"
                intent = {"metric": metric, "filters": {}, "group_by": group_by, "date_range": date_range}
                if ephemeral_expr:
                    intent["derived_expression"] = ephemeral_expr
                parser_used = "heuristic"
            else:
                ask = msg.split(":", 1)[1].strip() if ":" in msg else msg
                return {"clarification_required": True, "message": ask}
        else:
            return JSONResponse({"error": msg}, status_code=400)
    except Exception as exc:  # missing key, model, etc.
        return JSONResponse({"error": f"Parser unavailable: {exc}"}, status_code=500)

    # Optional DB-backed disambiguation
    try:
        from validation.disambiguator import disambiguate_filters  # type: ignore

        intent = disambiguate_filters(intent)
    except Exception:
        pass

    # Validate and resolve dates
    try:
        validated = validate_intent(intent, config)
    except (IntentValidationError, RuntimeError) as exc:
        return JSONResponse({"error": f"Invalid intent: {exc}"}, status_code=400)

    # Build SQL and run
    try:
        from builder.sql_builder import build_sql  # type: ignore
        from sqlalchemy import create_engine  # type: ignore
    except Exception as exc:
        return JSONResponse({"error": f"Execution unavailable: {exc}"}, status_code=500)

    try:
        sel, params = build_sql(validated, config, db_type='sqlite')
        engine = create_engine('sqlite:///enhanced_sales.db')
    except Exception as exc:
        return JSONResponse({"error": f"SQL build error: {exc}"}, status_code=400)

    # Execute
    rows: List[Dict[str, Any]] = []
    try:
        with engine.connect() as conn:
            res = conn.execute(sel, params)
            rows = [dict(r._mapping) for r in res]
    except Exception as exc:
        return JSONResponse({"error": f"Query execution error: {exc}"}, status_code=500)

    # Build chart HTML and return as base64 for embedding (iframe srcdoc on client)
    chart_info: Dict[str, Any] = {}
    chart_b64: Optional[str] = None
    try:
        from chart.chart_builder import build_chart  # type: ignore

        chart_info = build_chart(intent=validated, results=rows, output_path='last_query_chart.html', include_base64=True)
        chart_b64 = chart_info.get("html_base64")
    except Exception:
        chart_b64 = None

    return {
        "parser": parser_used,
        "intent": intent,
        "resolved_dates": validated.get("resolved_dates"),
        "rows": rows,
        "chart_type": chart_info.get("chart_type"),
        "chart_html_base64": chart_b64,
    }


# Serve static UI from /web
static_dir = Path(__file__).resolve().parent.parent / "web"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
