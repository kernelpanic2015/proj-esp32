#!/usr/bin/env python3
"""Bounded serial capture for non-interactive/Aurora ESP32 jobs."""

import argparse
import sys
import time

import serial


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--expect", action="append", default=[])
    args = parser.parse_args()

    seen = {marker: False for marker in args.expect}
    end = time.time() + args.seconds

    with serial.Serial(args.port, args.baud, timeout=0.25) as ser:
        # Do not intentionally hold the ESP32 in reset/bootloader mode.
        ser.dtr = False
        ser.rts = False
        while time.time() < end:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode(errors="replace").rstrip()
            print(line, flush=True)
            for marker in seen:
                if marker in line:
                    seen[marker] = True

    missing = [marker for marker, found in seen.items() if not found]
    if missing:
        print("SERIAL_EXPECT_MISSING=" + ",".join(missing), file=sys.stderr)
        return 1

    if seen:
        print("SERIAL_EXPECT_OK=" + ",".join(seen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
