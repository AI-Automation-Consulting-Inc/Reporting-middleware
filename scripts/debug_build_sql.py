import json
import traceback
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# ensure repo root is on sys.path so local packages (builder, nlp, validation) can be imported
sys.path.insert(0, str(ROOT))

print('CWD:', os.getcwd())
print('sys.path[0]:', sys.path[0])
print('Files in cwd:', os.listdir('.'))

cfg = json.loads((ROOT / 'config_store' / 'tenant1.json').read_text(encoding='utf-8-sig'))
intent = {'metric':'revenue','filters':{},'group_by':'product_name','resolved_dates':{'start_date':'2024-11-23','end_date':'2025-11-23'}}

try:
    from builder.sql_builder import build_sql
    sel, params = build_sql(intent, cfg, db_type='sqlite')
    from sqlalchemy import create_engine
    engine = create_engine('sqlite://')
    compiled = sel.compile(dialect=engine.dialect, compile_kwargs={'literal_binds': True})
    print('Compiled SQL:')
    print(str(compiled))
    print('Params:', params)
except Exception:
    traceback.print_exc()
