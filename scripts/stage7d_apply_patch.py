from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(rel):
    return (ROOT / rel).read_text(encoding='utf-8')

def write(rel, text):
    p = ROOT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding='utf-8')

def replace_once(rel, old, new):
    text = read(rel)
    if old not in text:
        raise SystemExit(f'missing anchor in {rel}: {old[:120]!r}')
    write(rel, text.replace(old, new, 1))

# Files are written by the Stage 7D execution job after preflight inspection.
print('STAGE7D_PATCH_HELPER_READY')
