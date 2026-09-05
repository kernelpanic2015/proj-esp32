from pathlib import Path
import re


def replace_once(s, old, new, label):
    if old not in s:
        raise SystemExit(f'missing {label}')
    return s.replace(old, new, 1)

p = Path('include/project_config.h')
s = p.read_text()
s = replace_once(
    s,
    'constexpr uint32_t HEARTBEAT_INTERVAL_MS = 10000;',
    'constexpr uint32_t HEARTBEAT_INTERVAL_MS = 10000;\nconstexpr uint16_t MQTT_BUFFER_SIZE = 4096;',
    'mqtt buffer config')
p.write_text(s)

p = Path('src/main.cpp')
s = p.read_text()
s = replace_once(s, 'mqttClient.setBufferSize(2048);',
                 'mqttClient.setBufferSize(ProjectConfig::MQTT_BUFFER_SIZE);',
                 'mqtt buffer setup')
p.write_text(s)

p = Path('platformio.ini')
s = p.read_text()
def set_env(text, env, version, build):
    pat = r'(\[env:' + re.escape(env) + r'\]\n)(.*?)(?=\n\[env:|\Z)'
    m = re.search(pat, text, re.S)
    if not m:
        raise SystemExit('missing env ' + env)
    block = m.group(2)
    block, n1 = re.subn(r'-DPROJ_FW_VERSION=\\"[^\n]+?\\"', '-DPROJ_FW_VERSION=\\"' + version + '\\"', block, count=1)
    block, n2 = re.subn(r'-DPROJ_FW_BUILD=\d+', '-DPROJ_FW_BUILD=' + str(build), block, count=1)
    if n1 != 1 or n2 != 1:
        raise SystemExit('version/build missing in ' + env)
    return text[:m.start(2)] + block + text[m.end(2):]
s = set_env(s, 'nodemcu-32s-signed-update-test', '0.1.24', 25)
s = set_env(s, 'nodemcu-32s-remote-update-test', '0.1.24-remote-test', 25)
s = set_env(s, 'nodemcu-32s-remote-target-test', '0.1.25', 26)
p.write_text(s)

p = Path('docs/runtime-test-log.md')
s = p.read_text()
if 'Stage 6E first physical attempt — partial / payload budget corrected' not in s:
    s += '''\n\n### Stage 6E first physical attempt — partial / payload budget corrected\n\n- Signed `0.1.23-remote-test/build 24` installed and reached `PENDING_VERIFY -> VALID`.\n- Controlled Wi-Fi disconnect was physically observed: HTTP became unavailable, Wi-Fi reconnect work stayed suppressed for the test window, then TaskScheduler issued one reconnect attempt and recorded one success.\n- After recovery, `connectivity` returned to `ONLINE/OK`, Supervisor returned to `RUNNING/OK`, MQTT reconnected, and the Wi-Fi reconnect work task returned to disabled.\n- The proof then exposed a separate telemetry budget regression: `/api/status` had grown to 2199 bytes while PubSubClient remained configured with a 2048-byte buffer, so scheduled telemetry attempts correctly ran but `publish()` returned false.\n- The buffer is therefore promoted to an explicit 4096-byte project setting before repeating the telemetry and clean-target proof. This is a transport payload-budget correction, not a Wi-Fi scheduler failure.\n'''
p.write_text(s)

p = Path('docs/architecture.md')
s = p.read_text()
if 'MQTT telemetry payload budget' not in s:
    s += '''\n\n#### MQTT telemetry payload budget\n\nThe common `/api/status` document is also used as the current MQTT telemetry payload. Stage 6E added Wi-Fi runtime observability and made the document 2199 bytes, exceeding the previous 2048-byte PubSubClient buffer. The buffer is now an explicit 4096-byte project setting. This preserves the current shared-status contract with headroom, while a future telemetry-schema stage may intentionally separate compact periodic telemetry from the full diagnostic status document as the component registry grows.\n'''
p.write_text(s)

print('STAGE6E_PAYLOAD_FIX_PATCH_OK')
