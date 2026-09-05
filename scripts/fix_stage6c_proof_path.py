#!/usr/bin/env python3
from pathlib import Path


def replace_once(path: str, old: str, new: str):
    p = Path(path)
    text = p.read_text()
    if old not in text:
        raise SystemExit(f"pattern not found in {path}: {old[:120]!r}")
    p.write_text(text.replace(old, new, 1))


# 1) Complete the integration points that the first physical attempt proved missing.
main = Path("src/main.cpp")
text = main.read_text()
old = '''  json += "\\\"components\\\":" + runtimeComponents.statusJson() + ",";\n  json += "\\\"event_bus\\\":{\\\"pending\\\":" + String(runtimeEvents.pending()) + ",\\\"dropped\\\":" + String(runtimeEvents.dropped()) + "},";\n'''
new = '''  json += "\\\"components\\\":" + runtimeComponents.statusJson() + ",";\n  json += "\\\"supervisor\\\":" + runtimeSupervisor.statusJson() + ",";\n  json += "\\\"event_bus\\\":{\\\"pending\\\":" + String(runtimeEvents.pending()) + ",\\\"dropped\\\":" + String(runtimeEvents.dropped()) + "},";\n'''
if '"supervisor":' not in text:
    if old not in text:
        raise SystemExit("status supervisor insertion point not found")
    text = text.replace(old, new, 1)

endpoint = '''  server.on("/api/test/mqtt/disconnect", HTTP_POST, [](AsyncWebServerRequest* request) {\n    mqttReconnectSuppressedUntil = millis() + 8000UL;\n    mqttClient.disconnect();\n    request->send(202, "application/json",\n                  "{\\\"accepted\\\":true,\\\"reconnect_suppressed_ms\\\":8000}");\n  });\n'''
if '/api/test/mqtt/disconnect' not in text:
    marker = '''    request->send(ok ? 202 : 500, "application/json",\n                  ok ? "{\\\"published\\\":true}" : "{\\\"published\\\":false}");\n  });\n#endif\n'''
    replacement = marker.replace('\n#endif\n', '\n\n' + endpoint + '#endif\n')
    if marker not in text:
        raise SystemExit("test endpoint insertion point not found")
    text = text.replace(marker, replacement, 1)
main.write_text(text)

# 2) Advance controlled build identities section-by-section. Build 19 is already
# physically consumed by the first lab attempt, so the retry must be monotonic.
ini = Path("platformio.ini")
lines = ini.read_text().splitlines()
targets = {
    "env:nodemcu-32s-signed-update-test": ("0.1.19", 20),
    "env:nodemcu-32s-remote-update-test": ("0.1.19-remote-test", 20),
    "env:nodemcu-32s-remote-target-test": ("0.1.20", 21),
}
current = None
seen = set()
out = []
for line in lines:
    if line.startswith("[") and line.endswith("]"):
        current = line[1:-1]
    if current in targets:
        version, build = targets[current]
        if "-DPROJ_FW_VERSION=" in line:
            line = f'    -DPROJ_FW_VERSION=\\"{version}\\"'
            seen.add((current, "version"))
        elif "-DPROJ_FW_BUILD=" in line:
            line = f"    -DPROJ_FW_BUILD={build}"
            seen.add((current, "build"))
    out.append(line)
for env in targets:
    if (env, "version") not in seen or (env, "build") not in seen:
        raise SystemExit(f"missing build profile fields for {env}")
ini.write_text("\n".join(out) + "\n")

# 3) Record the partial physical attempt immediately instead of rewriting history.
runtime_log = Path("docs/runtime-test-log.md")
text = runtime_log.read_text()
marker = "### Stage 6C first physical attempt — partial / corrected"
if marker not in text:
    text += '''\n### Stage 6C first physical attempt — partial / corrected\n\n- Signed `0.1.18-remote-test/build 19` installed successfully on `app1` and completed `PENDING_VERIFY -> VALID`.\n- `/api/supervisor` physically reported `RUNNING/OK` with the `connectivity` component `ONLINE/OK`; EventBus remained at zero dropped events.\n- The planned controlled MQTT interruption could not run because the lab-only `/api/test/mqtt/disconnect` route had not actually been inserted into `main.cpp`; the endpoint returned HTTP 404.\n- No production fault occurred. The device remained `ONLINE` with MQTT/TLS connected.\n- The source was corrected before retrying the degradation/recovery proof, and test build numbers were advanced so monotonic OTA ordering remains valid.\n'''
runtime_log.write_text(text)

bootstrap = Path("docs/BOOTSTRAP.md")
text = bootstrap.read_text()
marker = "## Stage 6C live lab state after first proof attempt"
if marker not in text:
    text += '''\n\n## Stage 6C live lab state after first proof attempt\n\nCanonical source baseline remains `0.1.17/build 18`, but the physical ESP32 is temporarily running the signed lab image `0.1.18-remote-test/build 19` on `app1`, native state `VALID`, `ONLINE` with MQTT/TLS connected. Supervisor is physically active and reports `RUNNING/OK`. The first degradation test stopped safely because the intended test-only MQTT disconnect endpoint returned 404; source is corrected and the retry uses higher monotonic builds.\n'''
bootstrap.write_text(text)

architecture = Path("docs/architecture.md")
text = architecture.read_text()
marker = "Stage 6C proof-note:"
if marker not in text:
    text += '''\n\nStage 6C proof-note: the first signed lab image physically validated Supervisor `RUNNING/OK`, but the controlled MQTT-disconnect route was missing due to an integration patch mismatch. The proof was stopped without simulating success; the route and `/api/status.supervisor` embedding were corrected and the retry uses fresh monotonic builds.\n'''
architecture.write_text(text)

print("STAGE6C_PROOF_PATH_FIXED")
