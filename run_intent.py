import argparse
import json
import sys
from pathlib import Path
from typing import Callable


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
        # parse_intent_with_llm uses RuntimeError for both clarification and other issues
        # Surface the message and abort (LLM-only mode)
        raise SystemExit(f"LLM error: {exc}")

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
    except Exception:
        pass

    # Execute and write results
    try:
        conn = engine.connect()
        res = conn.execute(sel, params)
        # SQLAlchemy Row objects expose a mapping interface via _mapping
        rows = [dict(r._mapping) for r in res]
        out_file = Path('last_query_results.json')
        out_file.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"\nWrote {len(rows)} rows to {out_file}")
        conn.close()
    except Exception as exc:
        print(f"Query execution error: {exc}")


if __name__ == "__main__":
    main()
