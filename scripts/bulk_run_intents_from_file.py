import subprocess
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV_PY = ROOT / '.venv' / 'Scripts' / 'python.exe'
RUN_INTENT = ROOT / 'run_intent.py'


def load_questions(path: Path):
    if not path.exists():
        raise FileNotFoundError(str(path))
    qs = []
    with path.open('r', encoding='utf-8') as f:
        for ln in f:
            ln2 = ln.strip()
            if not ln2:
                continue
            if ln2.startswith('#'):
                continue
            qs.append(ln2)
    return qs


def run_question(q):
    cmd = [str(VENV_PY), str(RUN_INTENT), '--question', q]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT), timeout=180)
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
    # detect whether the LLM asked for clarification (treat as 'clarification needed')
    clarification_needed = False
    stderr_txt = (proc.stderr or "").strip()
    if stderr_txt:
        if 'clarif' in stderr_txt.lower() or 'needs clarification' in stderr_txt.lower():
            clarification_needed = True

    res = {
        'question': q,
        'returncode': proc.returncode,
        'stdout': out,
        'stderr': proc.stderr,
        'parsed_intent': parsed,
        'parse_error': parse_error,
        'clarification_needed': clarification_needed,
    }
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-f', '--file', default='tests/intent_test_cases.txt', help='File with one question per line')
    ap.add_argument('-o', '--out', default='results_from_file.jsonl', help='Output results file name')
    ns = ap.parse_args()
    qfile = ROOT / ns.file
    questions = load_questions(qfile)

    out_file = ROOT / ns.out
    failures = []
    with out_file.open('w', encoding='utf-8') as f:
        for q in questions:
            print('Running:', q)
            r = run_question(q)
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            # Treat LLM clarification responses as 'clarification_needed' not failures
            if (r.get('returncode') != 0 or r.get('parsed_intent') is None) and not r.get('clarification_needed'):
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
                so = (f.get('stdout') or '').splitlines()
                print('  stdout (first 3 lines):')
                for l in so[:3]:
                    print('   ', l)


if __name__ == '__main__':
    main()
