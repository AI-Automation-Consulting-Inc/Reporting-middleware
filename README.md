# Report Middleware - Learning Guide

Natural language to SQL reporting middleware with LLM-powered intent parsing, schema-aware validation, and intelligent chart generation.

## Overview

This system interprets natural language queries, validates them against your tenant schema, generates parameterized SQL, executes on SQLite, and returns both data and interactive Plotly charts. It uses OpenAI's GPT-4 for intent parsing and chart type selection.

## Architecture

### Components

1. **Intent Parser** (`nlp/llm_intent_parser.py`)
   - Uses OpenAI GPT-4o-mini (temperature=0 for deterministic output)
   - Converts NL queries to structured JSON intent
   - Schema-aware: only uses metrics/dimensions from tenant config
   - Returns: `{metric, filters, group_by, date_range}`

2. **Validator** (`validation/validator.py`)
   - Validates parsed intent against tenant config
   - Resolves date ranges (calendar months, relative periods)
   - Disambiguates filter values using DB lookups

3. **SQL Builder** (`builder/sql_builder.py`)
   - Generates parameterized SQLAlchemy queries
   - Handles filters from multiple dimension tables
   - Supports ephemeral derived expressions (e.g., "average revenue per sales person")
   - Auto-detects join keys via foreign key analysis

4. **Chart Builder** (`chart/chart_builder.py`)
   - Infers chart type (bar, line, KPI, grouped bar)
   - Optional LLM-based chart selection for complex queries
   - Currency formatting ($x,xxx.xx for revenue/ARR/ACV)
   - Contextual titles showing active filters

5. **Web API** (`webapp/server.py`)
   - FastAPI endpoint: POST `/api/query`
   - Serves static UI at `/`
   - Returns: data rows + base64-encoded chart HTML

### Data Flow

```
User Query
    ↓
[LLM Intent Parser] → {metric, filters, group_by, date_range}
    ↓
[Validator] → Resolve dates, validate dimensions
    ↓
[SQL Builder] → Generate parameterized SQL with joins
    ↓
[SQLite Execution] → Return rows
    ↓
[Chart Builder] → Generate Plotly chart (optional LLM selection)
    ↓
[API Response] → {rows, chart_html_base64, intent}
```

## Configuration

### Tenant Config (`config_store/tenant1.json`)

```json
{
  "fact_table": "fact_sales_pipeline",
  "date_column": "sale_date",
  "dimensions": {
    "region": "geo_cluster",       // Maps to dim_region.geo_cluster (EMEA, AMER, APAC)
    "sales_rep": "rep_name",        // Maps to dim_sales_rep.rep_name
    "product_name": "product_name"
  },
  "metrics": {
    "revenue": "net_revenue",       // Simple column reference
    "deal_count": "COUNT(*)",       // Aggregation
    "revenue_per_customer": "SUM(net_revenue) / NULLIF(COUNT(DISTINCT customer_id), 0)"
  },
  "date_ranges": {
    "last_3_months": 90,
    "last_6_months": 182,
    "last_month": 30              // Calendar month when used with date_resolver
  }
}
```

### Database Schema

- Fact: `fact_sales_pipeline` (deals, revenue, pipeline stages)
- Dimensions:
  - `dim_region`: country, geo_cluster (EMEA/AMER/APAC), sales_area
  - `dim_sales_rep`: rep_name, team, quota
  - `dim_customer`: customer_name, industry, tier
  - `dim_product`: product_name, category, segment
  - `dim_channel`, `dim_pipeline_stage`, etc.

## LLM Configuration

### Intent Parser
- Model: `gpt-4o-mini` (via `OPENAI_INTENT_MODEL` env var)
- **Temperature: 0** (deterministic, no creativity)
- Response format: JSON object
- System prompt: Schema-aware rules, few-shot examples
- Timeout: Default OpenAI client timeout

### Chart Selector
- Model: `gpt-4o`
- **Temperature: 0** (consistent chart choices)
- Response format: `json_object` mode
- Selects: `bar`, `grouped_bar`, `line`, `pie`, `kpi`, `table`

## Key Features

### 1. Ephemeral Derived Metrics
Metrics computed on-the-fly without persisting to config:
```python
# Backend detects "average revenue per sales person"
ephemeral_expr = "SUM(f.net_revenue) / NULLIF(COUNT(DISTINCT f.sales_rep_id), 0)"
```

### 2. Multi-Dimension Filtering
SQL builder joins multiple dimension tables when filters and group_by span different tables:
```sql
SELECT d.rep_name AS group_col, SUM(net_revenue) AS metric
FROM fact_sales_pipeline f
JOIN dim_sales_rep d ON f.sales_rep_id = d.sales_rep_id
JOIN dim_region d0 ON f.region_id = d0.region_id
WHERE d0.geo_cluster = 'EMEA'
GROUP BY d.rep_name
```

### 3. Sales Rep Breakdown Charts
Auto-detects queries about per-rep metrics and generates grouped bar charts:
- Query: "average revenue per sales person by region"
- Result: Grouped bars showing each rep's revenue within each region

### 4. Calendar Month Support
Date resolver interprets "last month" as previous calendar month (e.g., Oct 1-31), not rolling 30 days.

### 5. Contextual Chart Titles
Titles show active filters: "Revenue by Sales Rep (Region: EMEA)"

## Quick Start

### CLI
```powershell
& .\.venv\Scripts\Activate.ps1
python run_intent.py --query "top 3 sales person from EMEA region" --clarify
```

Outputs: `last_query_results.json`, `last_query_chart.html`

### Web UI
```powershell
python -m uvicorn webapp.server:app --port 8000
```
Then open http://localhost:8000

### Example Queries

- "revenue from EMEA region last 6 months"
- "top 3 sales person from EMEA region"
- "monthly revenue trend for last year"
- "deal count by product category"
- "average revenue per sales person by region"

## Environment Variables

```powershell
$env:OPENAI_API_KEY = "sk-..."           # Required for LLM parsing
$env:OPENAI_INTENT_MODEL = "gpt-4o-mini" # Optional, default shown
$env:DUMMY_DB_NAME = "enhanced_sales.db" # Optional, for DB generation
```

## Development

### Adding Metrics
```powershell
python metric_cli.py --add "gross profit / number of companies" --key gross_margin_per_company
```

### Regenerating Database
```powershell
$env:FACT_ROW_COUNT = "5000"
python create_enhanced_dummy_db.py
```

### Testing
```powershell
pytest tests/                           # All tests
pytest tests/test_llm_validator_flow.py # LLM intent parsing
```

## Deployment Notes

- **Port**: Default 8000 (configurable)
- **Dependencies**: See `requirements.txt`
- **HTTPS**: Use reverse proxy (nginx, Caddy) for production
- **API Keys**: Store in environment, not in code
- **Database**: SQLite for demo; swap engine for production (PostgreSQL, etc.)

## Git Workflow

This project lives inside your existing repository:

```powershell
git add -A
git commit -m "feat: add LLM chart selection and rep breakdown"
git push origin WebUI  # Current branch
```

## Troubleshooting

**Q: Query returns no data**
- Check filter values match DB (e.g., "EMEA" vs "Germany")
- Verify dimension mapping in config (region → geo_cluster vs country)

**Q: Chart not showing**
- Hard refresh browser (Ctrl+Shift+R)
- Check server logs for chart build errors
- Verify Plotly is installed

**Q: LLM parsing fails**
- Confirm OPENAI_API_KEY is set
- Check model availability (gpt-4o-mini, gpt-4o)
- Review system prompt in `llm_intent_parser.py`

**Q: SQL errors on join**
- Check foreign key configuration in schema JSON
- Verify dimension column names in config match DB

## Temperature Settings

**Intent Parser**: Temperature **0.2**
- File: `nlp/llm_intent_parser.py`
- Reason: Slight creativity for better semantic mapping of user terms to schema dimensions/filters while preventing hallucination via strict prompt rules
- Output: Structured JSON matching schema exactly; stricter prompt prevents inventing non-existent values

**Chart Selector**: Temperature **0.2**  
- File: `chart/llm_chart_selector.py`
- Reason: Flexibility in chart type selection for complex queries while maintaining consistency
- Output: Chart type enum + breakdown options based on actual data

Both use temperature 0.2 to balance semantic understanding with deterministic behavior. Hallucination is prevented through explicit prompt rules requiring exact matches to config values.

# Open http://localhost:8000 in your browser
```

UI layout:
- Top: overview of middleware and DB
- Middle-left: interactive Plotly chart (rendered via iframe)
- Middle-right: data table for chart rows
- Bottom: NL query input with clarification loop
# Report Middleware

Natural-language analytics to SQL with a schema-aware LLM parser, deterministic SQLAlchemy builder, interactive chart generation, and acceptance tests.

## Overview
- Flow: NL question → Intent JSON → Validation/Disambiguation → SQLAlchemy (Select + params) → SQLite execution → JSON results + Interactive charts.
- Sources of truth:
  - `config_store/tenant1.json` (semantic model: metrics, dimensions, date ranges)
  - `config_store/tenant1_db_schema.json` (database schema snapshot)
- Key guarantees: deterministic SQL generation, parameterized queries, automatic chart generation, robust tests.

## Prerequisites
- Python 3.11+ (project tested on 3.13)
- An OpenAI API key in the environment (`OPENAI_API_KEY`).

## Setup
```powershell
# From repo root
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install openai python-dotenv sqlalchemy pytest pypdf "plotly[express]" kaleido numpy pandas

# Optional: verify OpenAI key (returns model list or fails fast)
# .\.venv\Scripts\python.exe .\nlp\check_openai_key.py
```

## Configuration
- Edit `config_store/tenant1.json` to adjust metrics/dimensions/date ranges.
- The DB schema snapshot `config_store/tenant1_db_schema.json` is generated by the script below and used by the SQL builder.

## Generate/refresh DB schema snapshot
```powershell
.\.venv\Scripts\python.exe .\scripts\extract_db_schema.py
```

## Run a single question
```powershell
.\.venv\Scripts\python.exe .\run_intent.py -q "revenue from EMEA region for last 12 months"
```
- Outputs:
  - Compact and pretty intent JSON
  - Resolved dates
  - Compiled SQL (for visibility)
  - `last_query_results.json` with query results
  - `last_query_chart.html` with interactive Plotly chart (KPI/line/bar inferred from query type)

## Bulk run from test cases
```powershell
.\.venv\Scripts\python.exe .\scripts\bulk_run_intents_from_file.py -f tests\intent_test_cases.txt -o results_from_file.jsonl
```
- Produces one JSONL line per question with parse/build/execute results.
- Clarifications are flagged as `clarification_needed` and not counted as failures.

## Tests
```powershell
.\.venv\Scripts\python.exe -m pytest tests\ -v
```
- Acceptance tests in `tests/test_acceptance.py` verify:
  - Schema JSON presence and expected columns
  - Parser few-shots map to exact JSON contracts
  - Builder returns `(Select, params)` and executes
  - Trend and group_by queries return expected structure

## Key Files & Directories
- `nlp/llm_intent_parser.py` — schema-aware LLM parser with strict JSON output
- `validation/validator.py`, `validation/date_resolver.py`, `validation/disambiguator.py`
- `builder/sql_builder.py` — SQLAlchemy Core builder; prefers schema JSON for joins
- `scripts/` — bulk runner, schema extractor, SQL debug helper, examples
- `tests/` — unit + acceptance tests
- `design/DESIGN_SUMMARY.md` — architecture, components, and major issues fixed

## Troubleshooting
- If LLM returns clarifications for unsupported phrasing (e.g., specific quarters), the prompt maps common phrases to available ranges; extend `tenant1.json` or few-shot examples as needed.
- If schema differs from DB, regenerate `tenant1_db_schema.json`.
- If `OPENAI_API_KEY` is missing, set it in your environment or a `.env` file and load it in your shell.

## Quick Notes
- SQL is executed parameterized; compiled SQL is printed for debugging.
- The builder falls back to PRAGMA-based discovery only if schema JSON is absent.