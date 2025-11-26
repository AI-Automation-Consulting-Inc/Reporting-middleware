Preparing Final Message for User Review...
I'll show the three draft files here so you can review them before I commit them to design. Tell me any edits and I'll apply them, or say “write files and proceed” to commit.

LEARNINGS.md

File: design/LEARNINGS.md
Learnings — Chat-Based Analytics MVP
Overview

Purpose: Run a deterministic NL→intent→validated SQL pipeline for tenant tenant1 (embeddable chat widget). This document captures root causes found during design, fixes implemented in the MVP, remaining risks, and recommended next steps.
Root Causes Identified

Ambiguous user language vs strict schema: Users often say "sales", "revenue", or "ARR" interchangeably; without normalization this causes wrong metric selection.
Dimension name mismatch: Tenant config maps user-facing dimension keys to DB columns (e.g., region → country). Without mapping, validator rejects valid requests.
Date-range interpretation variance: Natural phrases like "last year" or "past 12 months" map differently unless canonicalized.
Filter value ambiguity & typos: Free-text filter values (company names, product names) cause either no-match or over-broad queries.
Hallucinated SQL risk when using LLMs: unconstrained generation can produce unknown columns or non-deterministic expressions.
Fixes Implemented (MVP)

Tenant-driven semantic model: drives allowed metrics, dimensions, fact table, date column, and canonical date ranges. This stops schema hallucinations.
Deterministic intent parser (mock for MVP): rule-based string matching for metric + dimension extraction and synonyms normalization.
Strict validator: enforces metric existence, dimension membership, and allowed date ranges. Returns safe, user-friendly errors.
SQL templates + deterministic builder: only replaces known placeholders ($metric_formula, $fact_table, $date_column, $filters, $start_date, $end_date) using string.Template.
Date resolver: canonical mappings last_12_months=365d, last_6_months=182d, last_3_months=90d.
Tenant column mapping: validator and builder use the config dimension mapping so region (user) becomes country (DB).
Example mappings (tenant1)

Metric mapping: "revenue" → net_revenue (config metrics.revenue).
Dimension mapping: "region" → country, "product_name" → product_name, "sales_rep" → rep_name.
Fact & date: fact_table = fact_sales_pipeline, date_column = sale_date.
Date ranges: last_12_months = 365 days, last_6_months = 182 days, last_3_months = 90 days.
Remaining Risks

Entity resolution for filter values: exact-match requirement will fail on typos, synonyms, partial names.
Multi-tenant schema drift: if tenants update mappings, running systems must reload or cache invalidation may cause mismatch.
Edge-case date phrases: "since Jan 2024" or fiscal year semantics are not yet supported.
LLM integration risk: switching from mock parser to LLM without strong output constraints will reintroduce hallucination risk.
Recommendations / Next Steps

Short-term (MVP → stabilization):
Add fuzzy matching and synonyms table for filter values (low → med effort).
Add dynamic tenant config reload + schema versioning to avoid drift (med effort).
Improve date parser to accept absolute dates and common phrases (med effort).
Medium-term:
Introduce a constrained LLM wrapper that returns only JSON matching a provided JSON schema; run schema validation server-side (med → high).
Implement an intent confirmation UI for ambiguous parses: show proposed structured intent and ask user to confirm (low effort UX).
Long-term:
Entity store for canonical customer/product names (sync from source-of-truth CRM), and alias resolution (high effort).
Clarifications vs Auto-resolve Policy (short)

Auto-resolve when:
Metric maps 1:1 to a configured metric (e.g., "revenue" → net_revenue).
Dimension name exists in tenant config and filter value exactly matches an existing DB value (or passes fuzzy-threshold).
Date phrase maps to one of the canonical ranges in date_ranges.
Require clarification when:
Metric is missing or ambiguous (e.g., "sales" — could be revenue or pipeline_value).
Filter field is not known in tenant config.
Filter value is ambiguous (multiple candidate matches) or below fuzzy-match threshold.
User requests unsupported operations (e.g., custom SQL, joins across unknown tables).
Decision guidance: prefer safe clarification over auto-execution if any of the above "require clarification" conditions are met. When clarifying, present short, localisable prompts: e.g., "Do you mean net_revenue (revenue) or pipeline_value (pipeline value)?"

Quick actionables

Add fuzzy alias table and a small confirmation step for ambiguous matches.
Build a small test suite with tenant1 example queries (end-to-end from NL→chart).
Add documentation for tenant config schema and config reload behavior in design.
prompt_templates.md

File: design/prompt_templates.md
SYSTEM PROMPT (machine-readable)

You are a deterministic intent parser for a single tenant. Always output only valid JSON following the "OUTPUT_SCHEMA" exactly. Use tenant schema mappings for metrics and dimensions. Do not produce SQL, natural language, or explanations. If you cannot map an element, return an "error" object with a clear code and message (see schema). Do not invent new fields.

TENANT SCHEMA (tenant1)
{
"fact_table": "fact_sales_pipeline",
"date_column": "sale_date",
"metrics": {
"revenue": "net_revenue",
"arr": "arr",
"acv": "acv",
"gross_margin": "gross_margin",
"avg_discount": "discount_rate",
"pipeline_value": "pipeline_value",
"deal_count": "COUNT(*)"
},
"dimensions": {
"customer_name": "customer_name",
"industry": "industry",
"customer_tier": "customer_tier",
"product_name": "product_name",
"product_category": "product_category",
"deal_status": "deal_status",
"pipeline_stage": "pipeline_stage",
"region": "country",
"geo_cluster": "geo_cluster",
"sales_rep": "rep_name",
"channel": "channel_name",
"stage_category": "stage_category",
"contract_type": "contract_type"
},
"allowed_operations": ["sum","avg","count"],
"date_ranges": {
"last_12_months": 365,
"last_6_months": 182,
"last_3_months": 90
}
}

OUTPUT_SCHEMA (exact JSON)

On success, return:
{
"metric": "<metric_key>", // one of keys in tenant.metrics (string)
"metric_formula": "<sql_expression>", // resolved formula, e.g. "net_revenue" or "unit_price * quantity" (string)
"operation": "sum|avg|count", // operation to apply (string)
"filters": { // optional, map of dimension_key -> string or array of strings
"customer_name": "Hindustan Aeronautics",
"product_name": "Landing Gear"
},
"group_by": "none|day|month|quarter|year|<dimension_key>", // default: month for trends
"date_range": "last_12_months|last_6_months|last_3_months|explicit",
"date_from": "YYYY-MM-DD", // present if date_range == explicit or resolved by resolver
"date_to": "YYYY-MM-DD"
}

On error, return exactly:
{
"error": {
"code": "INVALID_METRIC|INVALID_DIMENSION|INVALID_DATE_RANGE|AMBIGUOUS_VALUE|PARSE_FAILURE",
"message": "Human readable explanation (short).",
"details": { /* optional */ }
}
}

NORMALIZATION RULES / SYNONYMS (apply before mapping)

metric synonyms: { "sales": "revenue", "revenue": "revenue", "net sales": "revenue", "arr": "arr", "annual recurring revenue": "arr" }
dimension synonyms: { "country": "region", "region": "region", "rep": "sales_rep", "sales rep": "sales_rep", "product": "product_name" }
operation mapping: { "total": "sum", "sum": "sum", "average": "avg", "count": "count" }
date phrase mapping: { "last 12 months": "last_12_months", "past year": "last_12_months", "last 6 months": "last_6_months", "last quarter": "last_3_months" }
NORMALIZATION RULES (value cleaning)

Trim whitespace, collapse multiple spaces, title-case company/product names for DB equality checks (e.g., "hindustan aeronautics" -> "Hindustan Aeronautics").
For numeric ranges, parse and return explicit date_from/date_to only when absolute dates provided or when mapping is unambiguous.
FEW-SHOT EXAMPLES (NL -> JSON output)

Example 1
NL: "Revenue from customer Hindustan Aeronautics for Landing Gear over the last 12 months"
JSON (success):
{
"metric": "revenue",
"metric_formula": "net_revenue",
"operation": "sum",
"filters": {
"customer_name": "Hindustan Aeronautics",
"product_name": "Landing Gear"
},
"group_by": "month",
"date_range": "last_12_months",
"date_from": "",
"date_to": ""
}

Example 2
NL: "Average discount by product category in the last 6 months"
JSON (success):
{
"metric": "avg_discount",
"metric_formula": "discount_rate",
"operation": "avg",
"filters": {},
"group_by": "product_category",
"date_range": "last_6_months",
"date_from": "",
"date_to": ""
}

Example 3 (ambiguous metric -> clarification required)
NL: "Show me sales for Q1"
JSON (error):
{
"error": {
"code": "INVALID_METRIC",
"message": "Metric 'sales' is ambiguous. Did you mean 'revenue' or 'pipeline_value'?",
"details": { "candidates": ["revenue","pipeline_value"] }
}
}

Example 4 (unknown dimension)
NL: "Revenue by business unit for last year"
JSON (error):
{
"error": {
"code": "INVALID_DIMENSION",
"message": "Dimension 'business unit' is not available for this tenant.",
"details": { "available_dimensions": ["customer_name","industry","product_name","region", "sales_rep", "product_category", "customer_tier"] }
}
}

USER PROMPT TEMPLATE (to feed the intent parser)

Provide a single-string user question. The parser must return the JSON matching OUTPUT_SCHEMA. Use the tenant schema above for mapping. Example invocation payload:
{
"tenant": "tenant1",
"question": "<user natural language question>"
}

Notes for implementers

Always apply normalization rules first.
Map normalized metric/dimension keys to the tenant column names (use metrics[...] and dimensions[...]) only in the builder stage; intent JSON should use metric keys and dimension keys (as shown) plus metric_formula for the resolved expression.
The parser should never produce SQL or database column names in filters; keep filters as user-facing keys and values — the SQL builder will replace them using tenant mappings.
project_plan.md

File: design/project_plan.md
Project Plan — Chat-Based Analytics MVP

Goal: Deliver a deterministic NL→intent→validated SQL→chart flow for tenant1 per PRD. Plan split into phases with file-level tasks, effort estimates, and checkpoints.

Phase 1 — Discover & Prep (Checkpoint A)

Review PRD and tenant config (done) — produce design/* docs (this PR).
Files: design/LEARNINGS.md, design/prompt_templates.md, design/project_plan.md
Effort: Low
Checkpoint A: Approval of design docs.
Phase 2 — Schema & Dummy Data (Checkpoint B)
2. Create dummy DB generator that produces sales with 5k rows.

Effort: Medium
Checkpoint B: Generated DB runs sample queries.
Phase 3 — Core Backend Stubs (Checkpoint C)
3. FastAPI skeleton and routing: backend/main.py. Implement POST /query that orchestrates modules.

Files: backend/main.py
Effort: Low
DB connector: connector/db.py with run_query(sql: str) -> list.
Files: connector/db.py
Effort: Low
Checkpoint C: /query accepts a request and returns well-formed error or placeholder response.
Phase 4 — NLP Intent Parser (Checkpoint D)
5. Implement rule-based intent parser: (mock with normalization rules and synonyms).

Effort: Medium
Checkpoint D: Parser passes the 4 few-shot examples in design/prompt_templates.md.
Phase 5 — Validation & Date Resolver (Checkpoint E)
6. Validator: implements checks: metric existence, filter fields, allowed date ranges.

Effort: Low
Date resolver: mapping last_12_months/last_6_months/last_3_months to start/end dates.
Effort: Low
Checkpoint E: Valid intents produce (start_date, end_date) and pass validation.
Phase 6 — SQL Builder & Templates (Checkpoint F)
8. SQL templates: (T1/T2/T3 from PRD).

Effort: Low
SQL builder: chooses template, resolves $metric_formula using tenant1.metrics, renders safe $filters and dates. Use string.Template.
Effort: Medium
Checkpoint F: Generated SQL matches deterministic examples from PRD and is safe (no injection from user text).
Phase 7 — Charting & Response (Checkpoint G)
10. Chart generator: chart/chart.py with generate_chart_url(labels, values) per PRD.
- Files: chart/chart.py
- Effort: Low
11. Integrate end-to-end in backend/main.py: run parser → validator → builder → DB → chart → response proto {answer, chart_url}.
- Effort: Medium
- Checkpoint G: End-to-end test passes for 3 canonical queries.

Phase 8 — Testing & CI (Checkpoint H)
12. Tests: unit tests for parser, validator, date_resolver, sql_builder, and db connector.
- Files: tests/*
- Effort: Medium
13. CI: Add a basic GitHub Actions workflow to run linters and tests on PRs.
- Files: .github/workflows/ci.yml
- Effort: Low
- Checkpoint H: CI green on main branch.

Phase 9 — Hardening & UX (Optional, post-MVP)
14. Add fuzzy entity resolution + alias table and a short confirmation UI flow for ambiguous values.
- Files: validation/entity_resolver.py, small UI spec.
- Effort: High
15. Prepare LLM integration wrapper (strict output schema enforcement) for future parser replacement.
- Files: (wrapper), tests.
- Effort: High

Deliverables checklist (file-level)

backend/main.py — Low→Medium
connector/db.py — Low
chart/chart.py — Low
tests/* — Medium
.github/workflows/ci.yml — Low
Milestones & Acceptance Criteria

Milestone 1 (Checkpoint C): Basic API up and running (smoke test).
Milestone 2 (Checkpoint F): Deterministic SQL produced and executes against dummy DB.
Milestone 3 (Checkpoint G): End-to-end NL → chart_url with correct chart data.
Milestone 4 (Checkpoint H): Tests + CI pass.
Timing Guidance (example sprint plan)

Week 1: Phases 1–3 (Docs, dummy DB, API skeleton).
Week 2: Phases 4–5 (Parser, validator, date resolver).
Week 3: Phase 6 (SQL builder & templates) + tests.
Week 4: Phase 7–8 (charting, E2E, CI) and buffer for bug fixes.
Notes

Prioritise safe rejection/clarification over guessed fixes.
Keep tenant config authoritative; all runtime mapping must come from tenant1.json.
What's next (pick one)

Reply “edit X” with edits you want (X = LEARNINGS / PROMPT / PLAN) and I’ll update the draft.
Reply “write files and proceed” to commit these three files into design and I will then:
update llm_intent_parser.py to use the new system prompt and normalization rules,
run the bulk runner and report improvement,
update the todo list and continue with the implementation plan.
Which would you like?