import sqlite3
from pathlib import Path

db = Path('enhanced_sales.db')
if not db.exists():
    print('DB missing')
    raise SystemExit(1)

conn = sqlite3.connect(str(db))
cur = conn.cursor()
cur.execute("PRAGMA table_info('dim_product')")
cols = cur.fetchall()
print('dim_product columns:')
for c in cols:
    print(c)
conn.close()
