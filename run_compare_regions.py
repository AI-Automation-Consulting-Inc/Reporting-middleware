import json
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta

# Load tenant config
config = json.loads(Path("config_store/tenant1.json").read_text(encoding="utf-8-sig"))

fact_table = config.get("fact_table", "fact_sales_pipeline")
date_col = config.get("date_column", "sale_date")
metric_col = config.get("metrics", {}).get("revenue", "net_revenue")

# Determine cutoff date for last_6_months (use days defined in config)
days = config.get("date_ranges", {}).get("last_6_months", 182)
cutoff = (datetime.utcnow() - timedelta(days=days)).date().isoformat()

db_path = Path("enhanced_sales.db")
if not db_path.exists():
    raise SystemExit(f"Database not found: {db_path}\nRun the app or place the DB at this path.")

region_dim_table = 'dim_region'
region_dim_key = 'region_id'

sql = f"""
SELECT strftime('%Y-%m', f.{date_col}) AS month,
       r.country AS region,
       SUM(f.{metric_col}) AS revenue
FROM {fact_table} AS f
LEFT JOIN {region_dim_table} AS r ON f.{region_dim_key} = r.{region_dim_key}
WHERE f.{date_col} >= ?
GROUP BY month, region
ORDER BY month ASC, region ASC
"""

conn = sqlite3.connect(str(db_path))
conn.row_factory = sqlite3.Row
cur = conn.cursor()
cur.execute(sql, (cutoff,))
rows = cur.fetchall()
conn.close()

if not rows:
    print("No data returned for the given range and database.")
    raise SystemExit(0)

# Aggregate into a dict: months x regions
months = []
regions = []
data = {}
for r in rows:
    m = r["month"]
    reg = r["region"]
    rev = r["revenue"] or 0
    if m not in data:
        data[m] = {}
    data[m][reg] = rev
    if m not in months:
        months.append(m)
    if reg not in regions:
        regions.append(reg)

months.sort()
regions.sort()

# Print header
print("Monthly revenue by region (last 6 months, cutoff: %s)" % cutoff)
print()
print("Month", end="")
for reg in regions:
    print("\t", reg, end="")
print("\tTotal")

for m in months:
    total = 0
    print(m, end="")
    for reg in regions:
        val = data.get(m, {}).get(reg, 0)
        total += val
        print("\t", f"{val:.2f}", end="")
    print("\t", f"{total:.2f}")

# Also print JSON output
out = {"months": months, "regions": regions, "data": data}
print()
print("JSON:\n")
print(json.dumps(out, indent=2))
