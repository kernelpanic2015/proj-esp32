#!/usr/bin/env python3
"""Bounded serial capture for non-interactive/Aurora ESP32 jobs.

The port is configured with DTR/RTS deasserted *before* opening it. This avoids
creating an unintended reset pulse on ESP32 boards whose CP2102 DTR/RTS lines
are wired to EN/IO0 for automatic bootloader entry.
"""

import argparse
import sys
import time

import serial


def open_without_reset(port: str, baud: int) -> serial.Serial:
    ser = serial.Serial()
    ser.port = port
    ser.baudrate = baud
    ser.timeout = 0.25
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument("--expect", action="append", default=[])
    args = parser.parse_args()

    seen = {marker: False for marker in args.expect}
    end = time.time() + args.seconds

    ser = open_without_reset(args.port, args.baud)
    try:
        while time.time() < end:
            raw = ser.readline()
            if not raw:
                continue
            line = raw.decode(errors="replace").rstrip()
            print(line, flush=True)
            for marker in seen:
                if marker in line:
                    seen[marker] = True
    finally:
        ser.close()

    missing = [marker for marker, found in seen.items() if not found]
    if missing:
        print("SERIAL_EXPECT_MISSING=" + ",".join(missing), file=sys.stderr)
        return 1

    if seen:
        print("SERIAL_EXPECT_OK=" + ",".join(seen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
