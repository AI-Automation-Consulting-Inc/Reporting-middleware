Plan: Canonical Prompts & Schema Ingestion

TL;DR

Standardize the LLM system prompt, ingest the full tenant DB schema into a JSON config, then update the parser and SQL builder to consult that schema so the pipeline produces fewer clarifications and SQL errors. This reduces join/hinting mistakes and makes bulk tests reproducible.

Steps

1. Create schema extractor script
- Add `scripts/extract_db_schema.py` that connects to `enhanced_sales.db` and enumerates all tables.
- For each table, collect columns via `PRAGMA table_info('{table}')` and record: name, type, not-null flag, default value, and pk flag.
- Use `PRAGMA foreign_key_list('{table}')` to record declared FKs.
- Additionally infer likely foreign keys heuristically (e.g., `region_id` → `dim_region`) and mark these with `source: "inferred"`.
- Output a JSON at `config_store/tenant1_db_schema.json` containing `database`, `tables` (map of table → metadata), and `inferred_foreign_keys` if any.

2. Generate tenant schema JSON
- Run `scripts/extract_db_schema.py` to produce `config_store/tenant1_db_schema.json`.
- Inspect the file and commit it as a snapshot (or keep it generated at CI/startup depending on workflow).

3. Replace / canonicalize the system prompt
- Replace the `SYSTEM_PROMPT` in `nlp/llm_intent_parser.py` with the canonical prompt from `design/prompt_templates.md` (few-shots + strict JSON schema + machine-readable schema guidance).
- Keep `parse_intent_with_llm` interface unchanged.

4. Make the parser schema-aware
- Update `_summarize_config` (or add a new helper) to include a concise, machine-readable summary of `config_store/tenant1_db_schema.json`: tables, primary keys, and top columns (fact table + dim tables).
- Feed that summary into the user/system prompts so the LLM has authoritative table/column lists instead of partial lists.
- Expand `norm_map` and few-shot examples to cover common synonyms and ambiguous phrases seen in bulk runs.

5. Make the builder consult the schema JSON
- Update `builder/sql_builder.py` to prefer `config_store/tenant1_db_schema.json` for authoritative table/column lists and declared FKs.
- Keep fallback PRAGMA introspection for local dev but prefer the JSON for deterministic behavior (use `source` flag to prefer declared keys over inferred keys).
- Preserve the return signature `(Select, params)`.

6. Run bulk tests and iterate
- Re-run `scripts/bulk_run_intents_from_file.py` against `tests/intent_test_cases.txt` and write `results_from_file.jsonl`.
- Triage failures into: clarifications, parser JSON errors, SQL build errors, and query execution errors.
- Iterate on: prompt few-shots, `norm_map`, and `config_store/tenant1.json` dimension mappings.

7. Add acceptance checks
- Add simple acceptance/unit tests that assert:
  - `config_store/tenant1_db_schema.json` contains `fact_sales_pipeline` with expected id columns and `net_revenue` metric column.
  - Few-shot examples in `design/prompt_templates.md` parse into the exact JSON shown.
  - `builder/sql_builder.py` returns a parameterized Select and `params` for a canonical query.

Further Considerations

- Clarification policy: decide whether `clarification_required` should be surfaced to the end user or auto-resolved via DB-backed heuristics. Implement `validation/disambiguator.py` as the first-line auto-resolver and surface remaining clarifications.

- Schema cadence: snapshot `tenant1_db_schema.json` as a committed source-of-truth for repeatable tests; optionally regenerate on CI or developer startup to keep it fresh.

- FK inference accuracy: prefer declared PRAGMA FKs; when using heuristics, clearly mark `source: "inferred"` so downstream code knows when to be cautious.

- Backwards compatibility: keep PRAGMA-based builder fallback until JSON-driven builder is validated by tests.

Next Actions (suggested)

- Implement `scripts/extract_db_schema.py` and run it to generate `config_store/tenant1_db_schema.json`.
- After the JSON is produced, update the `SYSTEM_PROMPT` in `nlp/llm_intent_parser.py` and re-run the bulk tests.

Would you like me to implement the extractor now and generate the JSON file, or would you prefer I only create the script and let you run it locally?
