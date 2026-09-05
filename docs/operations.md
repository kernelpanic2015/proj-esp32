# Operations

## Local working tree

```bash
cd /home/kernelpanic/Projects/proj-esp32
```

The project uses a dedicated PlatformIO virtual environment and wrapper:

```bash
./scripts/pio
```

## PlatformIO

Build:

```bash
./scripts/pio run
```

Upload over CP2102:

```bash
./scripts/pio run -t upload --upload-port /dev/ttyUSB0
```

Erase flash intentionally:

```bash
./scripts/pio run -t erase --upload-port /dev/ttyUSB0
```

List devices:

```bash
./scripts/pio device list
```

## Serial observation

Interactive human use can use PlatformIO's monitor:

```bash
./scripts/pio device monitor -p /dev/ttyUSB0 -b 115200
```

For Aurora jobs this is not the preferred path because the PlatformIO monitor expects an interactive terminal. A previous non-interactive Aurora monitor job exited with failure even though the firmware was running correctly.

Use pyserial for deterministic capture under Aurora. Example pattern:

```python
import serial, time
s = serial.Serial('/dev/ttyUSB0', 115200, timeout=0.5)
end = time.time() + 8
while time.time() < end:
    line = s.readline().decode(errors='ignore').strip()
    if line:
        print(line)
s.close()
```

The verified smoke firmware produced normal ROM boot output followed by:

```text
ESP32_SMOKE_BOOT_OK
ESP32_SMOKE_HEARTBEAT_OK
```

## Aurora jobs

Commands to the notebook are submitted through issues in `kernelpanic2015/aurora-kpnote`.

Issue body must be strict `aurora.job.v1` JSON; do not wrap it in Markdown fences.

Example:

```json
{
  "schema": "aurora.job.v1",
  "name": "build-proj-esp32",
  "cwd": "/home/kernelpanic/Projects/proj-esp32",
  "argv": [
    "/bin/bash",
    "-lc",
    "./scripts/pio run"
  ],
  "timeout_seconds": 600
}
```

Add label:

`aurora:queued`

The Aurora Client updates the issue and posts a local job UUID after execution.

If Aurora Watch is unavailable, use the job UUID with the external read endpoint:

`https://jobs.omni-one.org/api/watch/jobs/{jobId}`

For important diagnostics, make the job capture stdout/stderr into a file and post that file to the issue using GitHub CLI. This avoids depending on a separate observation channel.

## Git workflow

Canonical remote:

`https://github.com/kernelpanic2015/proj-esp32.git`

The desired invariant is:

```text
local main == origin/main
```

Before builds driven from changes made directly on GitHub:

```bash
git pull --ff-only origin main
```

After validated local modifications:

```bash
git add ...
git commit -m '...'
git push origin main
```

Do not commit `.pio/` or `.venv-platformio/`.

## Safe iteration order

For changes that can affect boot/networking:

1. pull/sync source
2. compile
3. inspect warnings/errors
4. upload
5. capture serial boot
6. validate network services
7. only then push local-only corrections

USB remains the recovery path even after OTA is enabled.
