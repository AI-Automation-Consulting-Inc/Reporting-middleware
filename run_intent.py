import argparse
import json
import sys
from pathlib import Path
from typing import Callable

# Optional interactive clarify flow imports
try:
    from nlp.formula_parser import parse_nl_formula, FormulaParseError
    from config.config_updater import add_or_update_metric
    from nlp.intent_parser import parse_intent as heuristic_parse_intent
except Exception:
    parse_nl_formula = None  # type: ignore
    FormulaParseError = Exception  # type: ignore
    add_or_update_metric = None  # type: ignore
    heuristic_parse_intent = None  # type: ignore


def _load_validator():
    try:
        from validation.validator import validate_intent, IntentValidationError

        return validate_intent, IntentValidationError
    except Exception:
        try:
            from nlp.validator import validate_intent, IntentValidationError

            return validate_intent, IntentValidationError
        except Exception:
            from nlp.validator import validate_intent as _validate_intent

            def validate_intent(intent, config):
                _validate_intent(intent, config)
                # minimal resolved_dates placeholder
                return {**intent, "resolved_dates": {"date_range": intent.get("date_range")}}

            class IntentValidationError(RuntimeError):
                pass

            return validate_intent, IntentValidationError


def main():
    parser = argparse.ArgumentParser(description="Run intent parsing (LLM-only)")
    parser.add_argument("--question", "-q", type=str, help="Question to parse", required=False)
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="When set, abort on LLM clarification/error (LLM-only mode).",
    )
    parser.add_argument(
        "--clarify",
        action="store_true",
        help="Enable interactive clarification: accept NL formulas to add metrics and continue.",
    )

    args = parser.parse_args()

    config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))
    question = args.question or "Revenue from Hindustan Aeronautics for Landing Gear in the last 12 months"

    validate_intent, IntentValidationError = _load_validator()

    parser_used = None
    # LLM-only flow: call the LLM parser and abort on clarification or runtime errors
    try:
        from nlp.llm_intent_parser import parse_intent_with_llm
    except Exception as exc:
        raise SystemExit(f"LLM parser unavailable: {exc}")

    try:
        intent = parse_intent_with_llm(question, config)
        parser_used = "llm"
    except RuntimeError as exc:
        # LLM asked for clarification or failed. If interactive clarify is enabled, prompt user.
        if not args.clarify:
            raise SystemExit(f"LLM error: {exc}")

        print(f"LLM needs clarification: {exc}")
        if not (parse_nl_formula and add_or_update_metric):
            raise SystemExit("Interactive clarify not available (missing modules). Re-run without --clarify.")

        # Interactive loop: accept existing metric key or NL formula to add a new one
        while True:
            try:
                user_input = input(
                    "Enter a metric key to use, or provide a natural-language formula\n"
                    "(e.g., 'average revenue per customer'). Type 'q' to abort: "
                ).strip()
            except EOFError:
                raise SystemExit("Aborted (no input available)")

            if not user_input:
                print("Please enter a metric key or a formula, or 'q' to quit.")
                continue
            if user_input.lower() in ("q", "quit", "exit"):
                raise SystemExit("Aborted by user")

            chosen_metric = None
            # If user supplied an existing metric key
            if user_input in (config.get("metrics") or {}):
                chosen_metric = user_input
            else:
                # Treat as NL formula; parse and add to config
                try:
                    metric_key, expr = parse_nl_formula(user_input, schema=json.loads(Path("config_store/tenant1_db_schema.json").read_text(encoding="utf-8-sig")) if Path("config_store/tenant1_db_schema.json").exists() else {}, config=config)
                except FormulaParseError as e:
                    print(f"Could not parse formula: {e}")
                    continue
                try:
                    add_or_update_metric(metric_key, expr, path="config_store/tenant1.json")
                    # reload config to include new metric
                    config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))
                    print(f"Metric saved: {metric_key} := {expr}")
                    chosen_metric = metric_key
                except Exception as e:
                    print(f"Failed to save metric: {e}")
                    continue

            # Prefer re-running the LLM with updated config; fallback to heuristic
            try:
                intent = parse_intent_with_llm(question, config)
                # Force metric if LLM still doesn't pick it reliably
                if intent.get("metric") != chosen_metric:
                    intent["metric"] = chosen_metric
                parser_used = "llm+clarify"
                break
            except RuntimeError as rexc:
                print(f"LLM still needs clarification: {rexc}")
                if not heuristic_parse_intent:
                    # loop again for more input
                    continue
                try:
                    intent = heuristic_parse_intent(question, config)
                    intent["metric"] = chosen_metric
                    parser_used = "heuristic+clarify"
                    break
                except Exception as e:
                    print(f"Heuristic parse failed: {e}")
                    continue

    # DB-backed disambiguation: prefer values found in dim_region/ dim_customer
    try:
        from validation.disambiguator import disambiguate_filters

        intent = disambiguate_filters(intent)
    except Exception:
        # If disambiguator not available or DB missing, fall back to heuristics (no-op)
        pass

    try:
        validated = validate_intent(intent, config)
    except IntentValidationError as exc:
        raise SystemExit(f"Invalid intent: {exc}")
    except RuntimeError as exc:
        raise SystemExit(f"Invalid intent: {exc}")

    print(f"Parser used: {parser_used}")
    # Print a compact single-line intent JSON for easy grepping, then a pretty JSON
    compact_intent = json.dumps(intent, separators=(',', ':'), ensure_ascii=False)
    print("Intent:", compact_intent)
    print(json.dumps(intent, indent=2, ensure_ascii=False))
    compact_dates = json.dumps(validated.get("resolved_dates"), separators=(',', ':'), ensure_ascii=False)
    print("Resolved dates:", compact_dates)
    print(json.dumps(validated.get("resolved_dates"), indent=2, ensure_ascii=False))
    # Build SQL and execute it against the local DB if available.
    try:
        from builder.sql_builder import build_sql
        from sqlalchemy import create_engine
    except Exception:
        # builder not available — skip execution
        return

    try:
        sel, params = build_sql(validated, config, db_type='sqlite')
    except Exception as exc:
        print(f"SQL builder error: {exc}")
        return

    # print compiled SQL for debugging
    try:
        engine = create_engine('sqlite:///enhanced_sales.db')
        compiled = sel.compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True})
        print('\nCompiled SQL:')
        print(str(compiled))
    except Exception as e:
        print(f"[WARN] Could not print compiled SQL: {e}")

    # Execute and write results
    try:
        conn = engine.connect()
        res = conn.execute(sel, params)
        # SQLAlchemy Row objects expose a mapping interface via _mapping
        rows = [dict(r._mapping) for r in res]
        out_file = Path('last_query_results.json')
        out_file.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"\nWrote {len(rows)} rows to {out_file}")
        
        # Generate chart if chart module available
        try:
            from chart.chart_builder import build_chart
            chart_info = build_chart(
                intent=validated,
                results=rows,
                output_path='last_query_chart.html',
                include_base64=False,
            )
            print(f"Chart generated: {chart_info['chart_type']} → {chart_info['html_path']}")
        except Exception as chart_exc:
            print(f"Chart generation skipped: {chart_exc}")
        
        conn.close()
    except Exception as exc:
        print(f"Query execution error: {exc}")


if __name__ == "__main__":
    main()
