import sqlite3
con=sqlite3.connect('enhanced_sales.db')
cur=con.cursor()
cur.execute("PRAGMA table_info('fact_sales_pipeline')")
cols=cur.fetchall()
print('fact_sales_pipeline columns:')
for c in cols:
    print(c)
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
print('\nall tables:')
for t in cur.fetchall():
    print(t[0])
con.close()
