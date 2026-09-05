#!/usr/bin/env python3
"""Build a deterministic firmware release manifest and optionally sign it.

The signature covers the exact UTF-8 bytes of manifest.json. The manifest
contains the SHA-256 of firmware.bin, so the signature binds identity/version
metadata to the firmware image without requiring the whole image in memory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys


def sha256_file(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run(*args: str) -> None:
    subprocess.run(args, check=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--firmware", required=True, type=pathlib.Path)
    parser.add_argument("--output", required=True, type=pathlib.Path)
    parser.add_argument("--model", required=True)
    parser.add_argument("--hardware-revision", required=True, type=int)
    parser.add_argument("--version", required=True)
    parser.add_argument("--build", required=True, type=int)
    parser.add_argument("--channel", default="dev")
    parser.add_argument("--private-key", type=pathlib.Path)
    parser.add_argument("--public-key", type=pathlib.Path)
    args = parser.parse_args()

    firmware = args.firmware.resolve()
    if not firmware.is_file():
        parser.error(f"firmware not found: {firmware}")

    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    copied_firmware = out / "firmware.bin"
    shutil.copy2(firmware, copied_firmware)

    manifest = {
        "schema": 1,
        "model": args.model,
        "hardware_revision": args.hardware_revision,
        "version": args.version,
        "build": args.build,
        "channel": args.channel,
        "size": copied_firmware.stat().st_size,
        "sha256": sha256_file(copied_firmware),
        "file": "firmware.bin",
    }

    manifest_path = out / "manifest.json"
    manifest_bytes = (json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    manifest_path.write_bytes(manifest_bytes)

    if args.private_key:
        signature_path = out / "manifest.sig"
        run(
            "openssl", "dgst", "-sha256",
            "-sign", str(args.private_key.resolve()),
            "-out", str(signature_path),
            str(manifest_path),
        )
        if args.public_key:
            run(
                "openssl", "dgst", "-sha256",
                "-verify", str(args.public_key.resolve()),
                "-signature", str(signature_path),
                str(manifest_path),
            )

    print(manifest_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
