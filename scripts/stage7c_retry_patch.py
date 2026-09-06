from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def patch(rel, replacements):
    p = ROOT / rel
    text = p.read_text(encoding="utf-8")
    for old, new in replacements:
        if old not in text:
            raise SystemExit(f"missing anchor in {rel}: {old!r}")
        text = text.replace(old, new)
    p.write_text(text, encoding="utf-8")

patch("src/main.cpp", [
    ('/api/test/rules/input/delayed', '/api/test/rules/queue-input'),
])

patch("platformio.ini", [
    ('-DPROJ_FW_VERSION=\\"0.1.32\\"\n    -DPROJ_FW_BUILD=33',
     '-DPROJ_FW_VERSION=\\"0.1.34\\"\n    -DPROJ_FW_BUILD=35'),
    ('-DPROJ_FW_VERSION=\\"0.1.32-remote-test\\"\n    -DPROJ_FW_BUILD=33',
     '-DPROJ_FW_VERSION=\\"0.1.34-remote-test\\"\n    -DPROJ_FW_BUILD=35'),
    ('-DPROJ_FW_VERSION=\\"0.1.33\\"\n    -DPROJ_FW_BUILD=34',
     '-DPROJ_FW_VERSION=\\"0.1.35\\"\n    -DPROJ_FW_BUILD=36'),
])

patch("scripts/stage7c_physical_proof.sh", [
    ("'\"version\":\"0.1.31\"'", "'\"version\":\"0.1.33\"'"),
    ("'\"build\":32'", "'\"build\":34'"),
    ('--version 0.1.32-remote-test --build 33 --channel dev',
     '--version 0.1.34-remote-test --build 35 --channel dev'),
    ('--version 0.1.33 --build 34 --channel dev',
     '--version 0.1.35 --build 36 --channel dev'),
    ("wait_transition '0.1.32-remote-test' 33 app1",
     "wait_transition '0.1.34-remote-test' 35 app1"),
    ("'/api/test/rules/input/delayed'", "'/api/test/rules/queue-input'"),
    ("wait_transition '0.1.33' 34 app0",
     "wait_transition '0.1.35' 36 app0"),
    ("'\"version\":\"0.1.33\"'", "'\"version\":\"0.1.35\"'"),
    ("'\"build\":34'", "'\"build\":36'"),
])

print('STAGE7C_RETRY_PATCHED')
