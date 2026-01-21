# Schema Rules — tenant1

This is the per-DB copy of the LLM rule book tailored to `tenant1`.

## Fact & Dimensions
- Fact table: `fact_sales_pipeline`
- Date column: `sale_date`
- Dimensions available: customer_name, industry, customer_tier, product_name, product_category, deal_status, pipeline_stage, country, region(geo_cluster), geo_cluster, sales_rep, channel, stage_category, contract_type

## Metric Column Mappings (from config)
- revenue → `net_revenue`
- arr → `arr`
- acv → `acv`
- gross_margin → `gross_margin`
- avg_discount → `discount_rate`
- pipeline_value → `pipeline_value`
- deal_count → `COUNT(*)` (not a column - use COUNT(*) for counting deals)

## Region vs Country
- `region` values: EMEA, AMER, APAC (maps to `dim_region.geo_cluster`)
- `country` values include: United States, Canada, Germany, United Kingdom, India, Singapore, Australia (maps to `dim_region.country`)

## Derived Expression Templates
- Average revenue per product by region:
  - derived_expression: `SUM(f.net_revenue) / NULLIF(COUNT(DISTINCT f.product_id), 0)`
  - group_by: `region`
- Average revenue per product by country:
  - derived_expression: `SUM(f.net_revenue) / NULLIF(COUNT(DISTINCT f.product_id), 0)`
  - group_by: `country`
- Average ARR per customer by industry:
  - derived_expression: `SUM(f.arr) / NULLIF(COUNT(DISTINCT f.customer_id), 0)`
  - group_by: `industry`
- Average deals per sales person (no grouping - single aggregate number):
  - derived_expression: `COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT f.sales_rep_id), 0)`
  - group_by: `null`
  - Note: deal_count metric is COUNT(*), not a column
- Average deals per sales person by region:
  - derived_expression: `COUNT(*) * 1.0 / NULLIF(COUNT(DISTINCT f.sales_rep_id), 0)`
  - group_by: `region`
- Win rate by dimension (if requested):
   - derived_expression: `SUM(CASE WHEN f.deal_status = 'Won' THEN 1 ELSE 0 END) / NULLIF(COUNT(*), 0)`
   - group_by: e.g., `industry`, filters: `region` or `country`, plus date_range.
   - Note: confirm exact winning status label if different (e.g., 'Closed Won').

## Clarification
- Use structured yes/no clarification when ambiguous.
- If input includes `Clarification: yes`, emit the intent JSON instead of another clarification.

## Join Guidance
- Join required dimension tables separately when filters/group_by span different tables (e.g., `dim_region` + `dim_product`).

## Chart Guidance
- Grouped bar for breakdowns; line for month trends; KPI for summaries.

Keep this per-tenant rules doc aligned with `config_store/tenant1.json` and the actual DB (`enhanced_sales.db`).