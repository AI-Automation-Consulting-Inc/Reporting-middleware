import json
from pathlib import Path
import sqlite3
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parents[1]
config = json.loads((ROOT / "config_store" / "tenant1.json").read_text(encoding='utf-8-sig'))

fact_table = config.get("fact_table", "fact_sales_pipeline")
date_col = config.get("date_column", "sale_date")
metric_col = config.get("metrics", {}).get("revenue", "net_revenue")

days = config.get("date_ranges", {}).get("last_12_months", 365)
cutoff = (datetime.utcnow() - timedelta(days=days)).date().isoformat()

db_path = ROOT / "enhanced_sales.db"
if not db_path.exists():
    raise SystemExit(f"Database not found: {db_path}")

sql = f"""
SELECT p.product_name AS product, SUM(f.{metric_col}) AS revenue
FROM {fact_table} AS f
LEFT JOIN dim_product AS p ON f.product_id = p.product_id
WHERE f.{date_col} >= ?
GROUP BY product
ORDER BY revenue DESC
LIMIT 50
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

print(f"Top products by revenue since {cutoff} (last 12 months):\n")
total = 0
for r in rows:
    prod = r['product'] or 'Unknown'
    rev = r['revenue'] or 0
    total += rev
    print(f"{prod}: {rev:.2f}")

print('\nTotal across listed products: {:.2f}'.format(total))
