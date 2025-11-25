from pathlib import Path
try:
    from pypdf import PdfReader
except Exception:
    try:
        from PyPDF2 import PdfReader
    except Exception:
        raise

ROOT = Path(__file__).resolve().parents[1]
PDF = ROOT / '📘 PRD_ Chat-Based Analytics MVP (Python + n8n + Deterministic SQL).pdf'
OUT = ROOT / 'design' / 'PRD_text.md'

def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    texts = []
    for p in reader.pages:
        try:
            t = p.extract_text() or ''
        except Exception:
            t = ''
        texts.append(t)
    return '\n\n'.join(texts)

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if not PDF.exists():
        print('PDF not found:', PDF)
        return
    txt = extract_text(PDF)
    with OUT.open('w', encoding='utf-8') as f:
        f.write('# Extracted PRD text\n\n')
        f.write(txt)
    print('Wrote extracted text to', OUT)

if __name__ == '__main__':
    main()
