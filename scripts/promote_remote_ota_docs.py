from pathlib import Path

# docs/README.md
p = Path("docs/README.md")
s = p.read_text()
s = s.replace("- [ ] require signed package verification on-device before accepting firmware",
              "- [x] require signed package verification on-device before accepting firmware")
s = s.replace("- [ ] add remote signed manifest download and automatic/MQTT update triggers",
              "- [x] remote signed manifest check + firmware download/apply path validated on hardware\n- [ ] add MQTT and automatic triggers to the validated remote update service")
runtime = """## Current runtime state

Validated directly on the physical device on 2026-09-05 after the first remote signed OTA proof:

- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`
- hardware model: `proj-esp32-35`, revision `1`
- firmware: `0.1.8`, build `9`, channel `dev`
- running OTA partition: `app1`
- boot partition: `app1`
- next update partition: `app0`
- native image state: `VALID`
- FSM/system: `ONLINE`
- Wi-Fi: connected
- MQTT: connected
- MQTT transport: TLS
- remote OTA policy in the normal image: HTTPS-only

The remote OTA proof used a temporary lab transition image with HTTP enabled only for the LAN fixture. The ESP32 fetched a signed `manifest.json`, verified its ECDSA P-256 signature, downloaded `firmware.bin`, verified the signed SHA-256, installed to the inactive slot, booted `PENDING_VERIFY`, transitioned to `VALID`, and retained Wi-Fi plus NVS-backed MQTT/TLS configuration. The final `0.1.8/build 9` image rejected the same plain-HTTP manifest URL with HTTP 400.
"""
start = s.index("## Current runtime state")
end = s.index("## OTA partition layout", start)
s = s[:start] + runtime + "\n" + s[end:]
p.write_text(s)

# docs/BOOTSTRAP.md
p = Path("docs/BOOTSTRAP.md")
s = p.read_text()
baseline = """## Current firmware baseline — verified 2026-09-05

Current physical device state after the first remote signed OTA proof:

- model: `proj-esp32-35`
- hardware revision: `1`
- firmware: `0.1.8`
- build: `9`
- channel: `dev`
- running partition: `app1`
- boot partition: `app1`
- next update partition: `app0`
- native OTA image state: `VALID`
- system/FSM: `ONLINE`
- Wi-Fi: connected
- MQTT/TLS: connected
- hostname: `proj-esp32`
- mDNS: `proj-esp32.local`
- device ID: `10A2CCEF49C0`

The first remote signed OTA was physically proven with a temporary LAN release fixture. `0.1.7-remote-test/build 8` enabled HTTP only for the controlled transition; it fetched and verified the signed `0.1.8/build 9` manifest and image. The final normal image returned to the default HTTPS-only remote-update policy.

Resolved dependency baseline:

- arduino-fsm 2.2.0
- ESP_DoubleResetDetector 1.3.2
- WiFiManager 2.0.17
- PubSubClient 2.8.0
- AsyncTCP 3.5.0
- ESPAsyncWebServer 3.12.0
- WebSerial 2.1.2
- ArduinoJson 6.21.x
- ESPmDNS 2.0.0
- Preferences / WiFi / WiFiClientSecure / HTTPClient / Update from Arduino-ESP32

Latest normal build after remote-update integration:

- RAM: about 54.3 KiB / 320 KiB (16.6%)
- firmware: about 1.20 MiB / 1.6875 MiB application slot (about 67.8%)
"""
start = s.index("## Current firmware baseline — verified 2026-09-05")
end = s.index("## Flash layout — validated", start)
s = s[:start] + baseline + "\n" + s[end:]
old = """Validated endpoints include:

- `http://proj-esp32.local/`
- `http://proj-esp32.local/api/status`
- `http://proj-esp32.local/api/version`
- `http://proj-esp32.local/api/update/status`
- `http://proj-esp32.local/update`
- `POST http://proj-esp32.local/api/update/upload`
- `http://proj-esp32.local/webserial`
- `http://proj-esp32.local/config/mqtt`"""
new = """Validated endpoints include:

- `http://proj-esp32.local/`
- `http://proj-esp32.local/api/status`
- `http://proj-esp32.local/api/version`
- `http://proj-esp32.local/api/update/status`
- `http://proj-esp32.local/api/update/remote/status`
- `http://proj-esp32.local/update`
- `POST http://proj-esp32.local/api/update/prepare`
- `POST http://proj-esp32.local/api/update/upload`
- `POST http://proj-esp32.local/api/update/check`
- `POST http://proj-esp32.local/api/update/apply`
- `http://proj-esp32.local/webserial`
- `http://proj-esp32.local/config/mqtt`"""
s = s.replace(old, new)
sign_start = s.index("## Firmware signing")
sign_end = s.index("## Serial observation rule", sign_start)
sign = """## Firmware signing and remote OTA — validated

A local ECDSA P-256 signing keypair exists on `kpnote` outside the Git repository.

Rules and verified behavior:

- private key stays outside Git and has owner-only permissions;
- public key is committed under `keys/update-signing-public.pem`;
- `scripts/release_manifest.py` creates a deterministic manifest and signature;
- the ESP32 verifies the ECDSA signature before preparing an update;
- unsigned packages and invalid signatures are rejected;
- the streamed firmware SHA-256 must match the signed manifest before `Update.end()` accepts the image;
- Web upload and remote download share the same signed-package install path;
- remote `check` fetches `manifest.json` + `manifest.sig`, then `apply` downloads `firmware.bin`;
- default builds accept only HTTPS remote manifest URLs;
- a lab-only build flag can enable HTTP for controlled LAN tests;
- the first remote OTA proof completed `0.1.7-remote-test/app0/VALID -> 0.1.8/app1/PENDING_VERIFY -> VALID`;
- after the proof the final `0.1.8` image rejected the same HTTP manifest URL, confirming return to HTTPS-only policy.

Transport CA validation is still pending. Update authenticity is already protected independently by the signed manifest and signed firmware hash.
"""
s = s[:sign_start] + sign + "\n" + s[sign_end:]
next_start = s.index("## Immediate next steps")
next_end = s.index("## Source-of-truth invariant", next_start)
next_steps = """## Immediate next steps

1. add MQTT commands `firmware.check` / `firmware.update` as triggers into the already validated remote UpdateManager path;
2. add persisted automatic-check policy (channel, manifest URL, interval, enabled flag) in NVS without making local control depend on connectivity;
3. replace development `setInsecure()` with CA validation for MQTT and remote HTTPS;
4. harden MQTT with LWT and reconnect backoff/jitter;
5. continue modular runtime (`ComponentRegistry`, health model, Supervisor, local rules/scheduler);
6. mount LittleFS and add minimal recovery UI;
7. proceed to TFT/touch/microSD bring-up only after pinout confirmation.
"""
s = s[:next_start] + next_steps + "\n" + s[next_end:]
p.write_text(s)

# docs/ota.md
p = Path("docs/ota.md")
s = p.read_text()
s = s.replace("- release manifest generation/signature verification already validated on the build host\n- next security milestone: reject unsigned/invalid packages on the ESP32 itself before installation",
              "- release manifest generation/signature verification validated on the build host\n- on-device ECDSA P-256 manifest verification validated\n- unsigned/invalid packages rejected before installation\n- streamed firmware SHA-256 checked against the signed manifest before the image is accepted")
remote_start = s.index("## Remote distribution")
rollback_start = s.index("## Rollback smoke tests", remote_start)
remote = """## Remote distribution

The remote transport now reuses the same signed package verifier and install engine as Web OTA.

Validated API/control flow:

```text
POST /api/update/check  -> fetch manifest.json + manifest.sig
                         -> verify ECDSA/model/hw/channel/build
                         -> AVAILABLE

POST /api/update/apply  -> stream firmware.bin
                         -> SHA-256 == signed manifest
                         -> inactive OTA slot
                         -> PENDING_REBOOT
                         -> PENDING_VERIFY
                         -> VALID or bootloader rollback
```

`GET /api/update/remote/status` exposes the remote transport state independently from `/api/update/status`.

Default firmware accepts only HTTPS manifest URLs. A compile-time lab-only flag `PROJ_REMOTE_UPDATE_ALLOW_HTTP=1` exists solely so a temporary LAN fixture can prove the transport without creating a public release host. The physical proof used that transition flag, then verified that the final normal `0.1.8/build 9` image rejected the same HTTP URL.

The next transport work is not another OTA engine: MQTT and automatic policies will only trigger this already validated check/apply path.
"""
s = s[:remote_start] + remote + "\n" + s[rollback_start:]
if "## Remote signed OTA physical proof" not in s:
    s += """
## Remote signed OTA physical proof — 2026-09-05

The first end-to-end remote download was proven on the physical ESP32:

```text
0.1.6 build 7 / app1 / VALID
        -> signed local transition
0.1.7-remote-test build 8 / app0 / PENDING_VERIFY -> VALID
        -> POST /api/update/check
        -> fetch signed manifest from LAN fixture
        -> ECDSA verify
        -> AVAILABLE
        -> POST /api/update/apply
        -> stream + SHA-256 verify
0.1.8 build 9 / app1 / PENDING_VERIFY -> VALID
```

Final runtime was `ONLINE` with Wi-Fi and MQTT/TLS connected and NVS configuration preserved. The final normal image reported `http_allowed=false` and rejected the temporary plain-HTTP manifest URL with HTTP 400.
"""
p.write_text(s)

# docs/ota-test-log.md
p = Path("docs/ota-test-log.md")
s = p.read_text()
if "remote signed OTA check/apply proof" not in s:
    s += """
## 2026-09-05 — remote signed OTA check/apply proof

- Starting image: `0.1.6`, build `7`, `app1`, `VALID`, system `ONLINE`.
- A signed local Web transition installed `0.1.7-remote-test`, build `8`, to `app0`.
- The transition image exposed the new remote update service and enabled plain HTTP only through the controlled `PROJ_REMOTE_UPDATE_ALLOW_HTTP=1` test flag.
- Transition boot was observed as `app0/PENDING_VERIFY` and then `app0/VALID`.
- A temporary HTTP release fixture ran on the `kpnote` LAN address and served only the already signed test package files: `manifest.json`, `manifest.sig`, `firmware.bin`.
- `POST /api/update/check` returned `202`; the ESP32 fetched the manifest/signature itself, verified ECDSA P-256, and reached remote state `AVAILABLE`.
- `/api/update/status` reported `package_prepared=true`, candidate `0.1.8`, build `9`.
- `POST /api/update/apply` returned `202`; the ESP32 downloaded the firmware itself.
- The downloaded `1,205,552` byte image was streamed through the shared UpdateManager path and checked against signed SHA-256 `a6b50616635b2126d019f0c5a95afc3b04960f8120de1e44b8132cfaeddefcf7`.
- Target boot was observed as `0.1.8/build 9`, `app1/PENDING_VERIFY`, then `app1/VALID`.
- Final runtime remained `ONLINE`; Wi-Fi, MQTT, MQTT configuration and MQTT/TLS were all present.
- Final free heap observed: about `164 KiB`.
- The normal target image reported `http_allowed=false`.
- Repeating the temporary HTTP manifest check on the final image returned HTTP `400` with `manifest_url_invalid`, proving that HTTP enablement was confined to the lab transition image.
- Aurora proof job UUID: `dee9ce6c-2b88-4e23-96a0-7db026887780`, completed with exit code `0`.

This proves the transport-independent update architecture: the remote path does not implement a second OTA engine; it feeds the same signed verifier, streaming SHA-256 check, A/B install, application validation and rollback lifecycle already used by Web OTA.
"""
p.write_text(s)

# docs/ROADMAP.md
p = Path("docs/ROADMAP.md")
s = p.read_text()
s = s.replace("## Stage 1 — Firmware identity, partition policy and signing foundation [next]",
              "## Stage 1 — Firmware identity, partition policy and signing foundation [validated]")
s = s.replace("## Stage 2 — Update Manager state machine",
              "## Stage 2 — Update Manager state machine [validated]")
s = s.replace("## Stage 3 — Web update path",
              "## Stage 3 — Web update path [validated signed package path]")
s = s.replace("## Stage 4 — Boot validation and rollback",
              "## Stage 4 — Boot validation and rollback [validated]")
s = s.replace("## Stage 5 — MQTT and automatic update triggers",
              "## Stage 5 — Remote transport validated; MQTT and automatic triggers pending")
marker = "MQTT may request update actions but never transports the firmware payload.\n"
if "Remote signed check/apply has been proven" not in s:
    s = s.replace(marker, "Remote signed check/apply has been proven on the physical ESP32. MQTT and automatic policy remain triggers only; they must reuse that path.\n\n" + marker, 1)
p.write_text(s)

# Advance reusable smoke-test expectations to the next cycle after 0.1.8.
p = Path("scripts/smoke_remote_ota.sh")
s = p.read_text()
s = s.replace("'\"version\":\"0.1.6\"'", "'\"version\":\"0.1.8\"'")
s = s.replace("'\"build\":7'", "'\"build\":9'")
s = s.replace("wait_for_transition '0.1.7-remote-test' 8 app0", "wait_for_transition '0.1.9-remote-test' 10 app0")
s = s.replace("'\"candidate_build\":9'", "'\"candidate_build\":11'")
s = s.replace("wait_for_transition '0.1.8' 9 app1", "wait_for_transition '0.1.10' 11 app1")
p.write_text(s)

print("DOCS_AND_TESTS_UPDATED")
