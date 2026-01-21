# Development Guide

Local development setup for Report-Middleware with Windows and PowerShell.

## Prerequisites

- Python 3.10+ (recommended 3.11)
- Git
- OpenAI API key
- Optional: Docker for containerized testing

## Quick Setup (Windows)

### 1. Clone Repository

```powershell
git clone https://github.com/AI-Automation-Consulting-Inc/Reporting-middleware.git
cd Report-Middleware
```

### 2. Create Virtual Environment

```powershell
python -m venv .venv
& .\.venv\Scripts\Activate.ps1
```

If you get an execution policy error, run:
```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

**Important**: Ensure `requirements.txt` contains all necessary packages:
- fastapi
- uvicorn
- sqlalchemy
- pandas
- plotly
- openai (CRITICAL - must be present)
- python-dotenv
- pydantic

### 4. Create .env File

```powershell
# Copy example
Copy-Item .env.example .env

# Edit with your API key
notepad .env
# Add: OPENAI_API_KEY=sk-your-key-here
```

### 5. Generate Test Database

```powershell
python create_enhanced_dummy_db.py
```

This creates `enhanced_sales.db` with sample sales data.

## Running Locally

### Test Single Query (CLI)

```powershell
python run_intent.py --question "revenue by region for last 12 months" --clarify
```

This outputs:
- `last_query_results.json` - Query results
- `last_query_chart.html` - Interactive chart
- `last_query_debug.txt` - Debugging info

### Run Web Server

```powershell
python -m uvicorn webapp.server:app --host 127.0.0.1 --port 8003
```

Then open: `http://localhost:8003`

### Run Tests

```powershell
pytest tests/ -v
```

## Project Structure

```
nlp/                    # NLP parsing pipeline
  ├── llm_intent_parser.py    # OpenAI GPT-4o-mini for intent parsing
  ├── intent_parser.py        # Local parsing (fallback)
  ├── date_resolver.py        # Parse relative dates
  └── formula_parser.py       # Parse derived metrics

validation/             # Validation layer
  ├── validator.py            # Intent validation against schema
  └── disambiguator.py        # Filter value resolution

builder/                # SQL building
  ├── sql_builder.py          # SQLAlchemy query generation
  └── sql_templates.py        # SQL templates

chart/                  # Visualization
  ├── chart_builder.py        # Plotly chart generation
  └── llm_chart_selector.py   # LLM-based chart type selection

webapp/                 # Web API
  ├── server.py               # FastAPI app with /api/query endpoint
  └── index.html              # Frontend UI

tests/                  # Test suite
  ├── test_sql_builder.py
  ├── test_validator.py
  ├── test_date_resolver.py
  └── test_acceptance.py

config_store/           # Configuration
  ├── tenant1.json            # Tenant schema config
  └── schema_rules.md         # Schema documentation
```

## Key Development Tasks

### Add a New Metric

1. Edit `config_store/tenant1.json`:
```json
{
  "metrics": {
    "revenue": "net_revenue",
    "your_new_metric": "column_name"  // Add here
  }
}
```

2. Test with CLI:
```powershell
python run_intent.py --question "your_new_metric by region"
```

### Add a New Dimension

1. Ensure dimension table exists in SQLite schema
2. Add to `config_store/tenant1.json`:
```json
{
  "dimensions": {
    "your_dimension": "column_name"
  }
}
```

3. Update `builder/sql_builder.py` if join key differs from pattern

### Debug a Query

1. Run with `--clarify` flag:
```powershell
python run_intent.py --question "your query" --clarify
```

2. Check output files:
```powershell
cat last_query_debug.txt
cat last_query_results.json
```

3. Check logs in web server terminal for errors

### Test Chart Generation

Edit `chart/chart_builder.py` and add test case:
```powershell
pytest tests/test_chart_builder.py -v -k "test_name"
```

## Database Schema

### Fact Table: fact_sales_pipeline

| Column | Type | Notes |
|--------|------|-------|
| sale_id | INTEGER | Primary key |
| sales_rep_id | INTEGER | FK to dim_sales_rep |
| region_id | INTEGER | FK to dim_region |
| customer_id | INTEGER | FK to dim_customer |
| product_id | INTEGER | FK to dim_product |
| sale_date | DATE | Transaction date |
| net_revenue | DECIMAL | Revenue amount |
| deal_count | INTEGER | Number of deals |

### Dimension Tables

- `dim_sales_rep`: rep_name, team, quota
- `dim_region`: geo_cluster (EMEA/AMER/APAC), country
- `dim_customer`: customer_name, industry, tier
- `dim_product`: product_name, category, segment

## Common Commands

### Install New Package
```powershell
pip install package_name
pip freeze > requirements.txt
git add requirements.txt && git commit -m "Add package_name"
```

### Run Specific Test
```powershell
pytest tests/test_validator.py::test_validation_pass -v
```

### Format Code
```powershell
pip install black
black .
```

### Check Dependencies
```powershell
pip list
pip check
```

### Activate Virtual Environment (Fresh Terminal)
```powershell
& .\.venv\Scripts\Activate.ps1
```

## Troubleshooting

### "openai package not installed"
```powershell
pip install openai>=1.0.0
pip freeze > requirements.txt
```

### Port 8003 already in use
```powershell
# Find and kill process
Get-Process -Name python | Stop-Process -Force
```

### Database file missing
```powershell
python create_enhanced_dummy_db.py
```

### OpenAI API key error
1. Verify .env file exists and has correct key
2. Check key is valid: `sk-...` format
3. Test with: `python -c "from openai import OpenAI; client = OpenAI()"`

### Import errors in tests
```powershell
# Ensure you're in virtual environment
& .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Git Workflow

### Create Feature Branch
```powershell
git checkout -b feature/your-feature-name
```

### Commit Changes
```powershell
git add .
git commit -m "Describe your changes"
```

### Push to GitHub
```powershell
git push origin feature/your-feature-name
```

### Create Pull Request
Go to GitHub and create PR from your branch to `main`

### Before Deployment

```powershell
# Ensure main branch is current
git checkout main
git pull origin main

# Verify tests pass
pytest tests/ -v

# Update requirements if needed
pip freeze > requirements.txt
git add requirements.txt
git commit -m "Update dependencies"
git push origin main
```

## Next Steps

1. Read [README.md](README.md) for architecture overview
2. Review [DEPLOYMENT.md](DEPLOYMENT.md) for production deployment
3. Check `tests/` directory for example usage patterns
4. Explore `nlp/ArchitectureandPlan.md` for technical design

## Support

For issues or questions, check:
- `last_query_debug.txt` for error details
- Test files for example queries
- Existing GitHub issues
