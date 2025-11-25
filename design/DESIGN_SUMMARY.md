# Design Summary: Report Middleware

This document summarizes the architecture, components, workflows, and the major issues we fixed across the project. It complements the implementation notes and test coverage.

## Architecture Overview
- Goal: NL → Intent JSON → Validation/Disambiguation → SQLAlchemy builder → DB execution → JSON result.
- Source-of-truth: `config_store/tenant1.json` (semantic model) and `config_store/tenant1_db_schema.json` (database schema snapshot).
- Reliability: SQLAlchemy Core, parameterized queries, schema-aware joins, acceptance tests.

## Components

- `config_store/tenant1.json`
  - Defines `fact_table`, `date_column`, `dimensions`, `metrics`, and `date_ranges`.
  - Key decisions: dimensions map NL names to physical columns (e.g., `sales_rep` → `rep_name`), metrics include expressions (e.g., `deal_count`: `COUNT(*)`).

- `config_store/tenant1_db_schema.json`
  - Generated snapshot of DB tables/columns/PKs/FKs.
  - Used by the SQL builder for deterministic join inference and to avoid runtime PRAGMA queries.

- `nlp/llm_intent_parser.py`
  - LLM-only parser with canonical system prompt enforcing strict JSON schema.
  - Includes DB schema summary in the prompt for schema awareness.
  - Normalization map for common phrases (e.g., "last year" → "last 12 months").
  - Lenient mapping for unsupported phrasing (e.g., ignore "Top N"; map "current quarter" → `last_3_months`).

- `validation/validator.py`
  - Validates metric, dimensions, and date_range against tenant config.
  - Calls `validation/date_resolver.py` to resolve start/end dates and returns `resolved_dates` in the intent.

- `validation/date_resolver.py`
  - Converts configured ranges (e.g., `last_6_months`) to concrete `[start_date, end_date]`.

- `validation/disambiguator.py`
  - DB-backed heuristic to move region-like tokens into `region` and ensure exact matches for known customers/regions.

- `builder/sql_builder.py`
  - SQLAlchemy Core builder returning `(Select, params)`.
  - Uses `tenant1_db_schema.json` to:
    - List fact/Dim columns deterministically
    - Prefer declared FKs, then inferred FKs, then heuristics for joins
  - Supports strategies: summary, trend (`group_by = month`), group_by dimension.

- `run_intent.py`
  - CLI: parse with LLM → disambiguate → validate → build SQL → execute against `enhanced_sales.db` → write `last_query_results.json`.

- `scripts/`
  - `extract_db_schema.py`: Extracts DB schema to JSON snapshot.
  - `bulk_run_intents_from_file.py`: Batch runner for `tests/intent_test_cases.txt`, produces `results_from_file.jsonl`.
  - `debug_build_sql.py`: Compile/inspect generated SQL.
  - `extract_prd_pdf.py`: Extract PRD to `design/PRD_text.md`.
  - `revenue_by_product.py`: Example query runner.

- `tests/`
  - Unit: validator, date resolver, LLM-validator flow, builder.
  - Acceptance: schema presence, parser few-shots, builder contract, and basic executions.

## Major Issues Fixed

1. COUNT aggregation misuse
   - Symptom: `SUM(COUNT(*))` and similar invalid aggregates.
   - Fix: Metric expression router → `COUNT`, `AVG`, else `SUM` of configured expression.

2. Wrong column references
   - Symptom: Filtering `country` or `rep_name` directly on fact table (missing columns).
   - Fix: Builder now inspects schema JSON and joins proper dim tables when filters/group_by reference dim columns.

3. Non-deterministic PRAGMA introspection
   - Symptom: Runtime schema introspection per query caused performance variability and failures when DB missing.
   - Fix: Snapshot `tenant1_db_schema.json` loaded once and cached in memory; PRAGMA path kept as fallback.

4. Clarifications treated as failures
   - Symptom: LLM clarifications counted as failures in batch results.
   - Fix: `bulk_run_intents_from_file.py` now flags `clarification_needed` and excludes from failure counts. Prompt updated to map common phrases to supported ranges/metrics.

5. Date range normalization gaps
   - Symptom: "last year" / "last 2 years" and similar phrases caused clarifications.
   - Fix: Extended `date_ranges` (e.g., `last_24_months`) and normalization rules; lenient mapping (e.g., "current quarter" → `last_3_months`).

6. Parameterization and SQL safety
   - Symptom: Risks with string-based templating.
   - Fix: SQLAlchemy Core builder returns parameterized `Select` + `params` and executes via bound parameters.

## Workflows

- Single run
  ```powershell
  .\.venv\Scripts\python.exe .\run_intent.py -q "revenue from EMEA region for last 12 months"
  ```

- Bulk run
  ```powershell
  .\.venv\Scripts\python.exe .\scripts\bulk_run_intents_from_file.py -f tests\intent_test_cases.txt -o results_from_file.jsonl
  ```

- Regenerate schema snapshot
  ```powershell
  .\.venv\Scripts\python.exe .\scripts\extract_db_schema.py
  ```

## Test Status
- Full suite: 23/23 passed.
- Bulk run: 25/25 executed, 0 failures; a few legitimate clarifications remain (forward-looking ARR, specific quarters, unmapped hierarchy dimension, growth-rate).

## Next Steps
- Add optional feature flags for quarters/YTD and forward-looking projections.
- Extend metric catalog (growth rate, churned ARR, new logos) with definitions and tests.
- Consider a ranking/limit layer in the response semantics for "Top N" outputs.
