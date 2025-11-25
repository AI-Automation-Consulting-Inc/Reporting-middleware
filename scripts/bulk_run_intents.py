import subprocess
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PY = ROOT / '.venv' / 'Scripts' / 'python.exe'
RUN_INTENT = ROOT / 'run_intent.py'

questions = [
    "Total net revenue for last month",
    "Monthly net_revenue by region for last 12 months",
    "Revenue from EMEA region for last 6 months",
    "Most revenue generating region for last year",
    "Monthly revenue trend for product 'Product X' for last 6 months",
    "Revenue by sales rep for the last quarter",
    "Top 5 customers by revenue for last year",
    "Number of deals in pipeline_stage 'closed_won' in the last month",
    "Average ACV by sales rep for last 12 months",
    "Pipeline value by region for current quarter",
    "Renewal ARR for next 6 months by customer",
    "Revenue from sales rep Helena Gomez for last 6 months",
    "Revenue by channel for the last 3 months"
]


def run_question(q):
    cmd = [str(VENV_PY), str(RUN_INTENT), '--question', q]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=120)
    except Exception as e:
        return {'question': q, 'error': str(e)}

    out = proc.stdout or ""
    s = out.strip()
    parsed = None
    parse_error = None
    # First try: look for a single-line JSON object
    lines = [l for l in s.splitlines() if l.strip()]
    for l in lines:
        l2 = l.strip()
        if l2.startswith('{') and l2.endswith('}'):
            try:
                parsed = json.loads(l2)
            except Exception as e:
                parse_error = str(e)
            break
    # Fallback: extract the first JSON object by balancing braces
    if parsed is None and '{' in s:
        start = s.find('{')
        end = None
        depth = 0
        for idx, ch in enumerate(s[start:], start):
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = idx + 1
                    break
        if end:
            maybe = s[start:end]
            try:
                parsed = json.loads(maybe)
            except Exception as e:
                parse_error = str(e)
    res = {
        'question': q,
        'returncode': proc.returncode,
        'stdout': out,
        'stderr': proc.stderr,
        'parsed_intent': parsed,
        'parse_error': parse_error,
    }
    return res


def main():
    out_file = ROOT / 'results.jsonl'
    failures = []
    with out_file.open('w', encoding='utf-8') as f:
        for q in questions:
            print('Running:', q)
            r = run_question(q)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            if r.get('returncode') != 0 or r.get('parsed_intent') is None:
                failures.append(r)

    print('\nWrote results to', str(out_file))
    print('Ran', len(questions), 'questions — failures:', len(failures))
    if failures:
        print('\nFailures summary:')
        for f in failures:
            print('- Question:', f['question'])
            print('  returncode:', f.get('returncode'))
            if f.get('parse_error'):
                print('  parse_error:', f['parse_error'])
            else:
                # print small slice of stdout
                so = (f.get('stdout') or '').splitlines()
                print('  stdout (first 3 lines):')
                for l in so[:3]:
                    print('   ', l)


if __name__ == '__main__':
    main()
