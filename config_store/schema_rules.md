# Schema Rules (LLM Rule Book)

Purpose: Provide precise, non-ambiguous guidance for LLMs to map user intent to the actual database schema and tenant configuration. This rule book is included verbatim in prompts and should be kept in sync with the DB and config.

## Core Contracts
- Output format: single JSON object with keys: `metric`, `filters`, `group_by`, `date_range`, optional `derived_expression`.
- Never invent metric or dimension names; use only those in tenant config.
- Use fact-table aliases and IDs in derived expressions: `f.<col>` for fact columns; prefer `COUNT(DISTINCT f.<id_col>)` for denominators.

## Dimension Semantics
- `region` → geo clusters: EMEA, AMER, APAC.
- `country` → specific countries (e.g., United States, Canada, Germany).
- Use `country` when the user names a country; use `region` for clusters.

## Metric Column Mappings
- `revenue` → `net_revenue` (fact column)
- `arr` → `arr`
- `acv` → `acv`
- `deal_count` → `COUNT(*)` (not a column - this is an aggregation function)
- Prefer the actual column from config; do not use aliases like `revenue` directly in SQL.
- CRITICAL: If a metric maps to `COUNT(*)`, use `COUNT(*)` in derived expressions, NOT a column reference like `f.deal_count`.

## Date Ranges
- Map natural phrases: last month → `last_month` (calendar month), last year → `last_12_months`, last 6 months → `last_6_months`.
- If an unavailable range is requested, ask structured clarification.

## Derived Expressions Patterns
- Average X per Y: `SUM(f.<metric_col>) / NULLIF(COUNT(DISTINCT f.<y_id_col>), 0)` with appropriate `group_by`.
- SPECIAL CASE - Average deals per Y: Since deal_count = COUNT(*), use `COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT f.<y_id_col>), 0)`
- Examples:
  - Avg revenue per product by region → `SUM(f.net_revenue) / NULLIF(COUNT(DISTINCT f.product_id), 0)`, `group_by = region`.
  - Avg ARR per customer by industry → `SUM(f.arr) / NULLIF(COUNT(DISTINCT f.customer_id), 0)`, `group_by = industry`.
  - Avg deals per sales person (no grouping) → `COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT f.sales_rep_id), 0)`, `group_by = null`.
  - Avg deals per sales person by region → `COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT f.sales_rep_id), 0)`, `group_by = region`.
- Win rate (if requested and not defined as a metric): requires clarification. Standard definition:
   - `SUM(CASE WHEN f.deal_status = 'Won' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)`
   - Groupable by dimensions like `industry`, filterable by region/country/date.
   - If `deal_status` values differ, ask the user to confirm the winning status label.

## Clarification Protocol
- If ambiguous: return `{clarification_required:true, interpretation:"...", question:"Is this correct?"}`.
- If the user confirms ("yes"), output the full intent with derived_expression set.
 - If a metric term is not present in config (e.g., "win rate", "velocity", "median"), ask a yes/no clarification with your proposed formula.

## Multi-Dimension Joins
- Filters and group_by may come from different dimension tables; do not assume same table.
- Join each needed dimension via its foreign key from fact.

## Chart Guidance
- Use grouped bar for "per X by Y" when breakdown is requested.
- Use line for `group_by = month`.
- Use KPI when no `group_by`.

Keep this document updated whenever schema or config changes.