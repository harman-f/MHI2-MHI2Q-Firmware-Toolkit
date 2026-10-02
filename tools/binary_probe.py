#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Read-only probe for opaque firmware binaries and quickboot candidates."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path

MARKERS = {
    "elf": b"\x7fELF",
    "qnx_startup": bytes.fromhex("EB7EFF00"),
    "imagefs": b"imagefs",
    "android_boot": b"ANDROID!",
    "lzoz": b"LZOZ",
    "qssl_f3s": b"QSSL_F3S",
    "kernel_primary": b"KERNEL_PRIMARY",
    "kernel_recovery": b"KERNEL_RECOVERY",
}


def entropy_from_counts(counts: Counter[int], total: int) -> float:
    if not total:
        return 0.0
    return -sum((count / total) * math.log2(count / total) for count in counts.values())


def analyze_binary(
    path: Path,
    *,
    max_strings: int = 128,
    min_string: int = 5,
    max_string_length: int = 4096,
) -> dict:
    if max_strings < 0:
        raise ValueError("max_strings must be >= 0")
    if min_string <= 0:
        raise ValueError("min_string must be > 0")
    if max_string_length < min_string:
        raise ValueError("max_string_length must be >= min_string")

    size = path.stat().st_size
    sha = hashlib.sha256()
    counts: Counter[int] = Counter()
    marker_offsets = {name: [] for name in MARKERS}
    strings = []
    current = bytearray()
    current_start = 0
    current_truncated = False
    in_printable_run = False
    offset = 0
    head = b""
    tail = b""
    overlap = max(len(value) for value in MARKERS.values()) - 1
    previous = b""

    def finish_string() -> None:
        nonlocal current_truncated, in_printable_run
        if in_printable_run and len(current) >= min_string and len(strings) < max_strings:
            entry = {
                "offset": current_start,
                "text": current.decode("ascii", errors="replace"),
            }
            if current_truncated:
                entry["truncated"] = True
            strings.append(entry)
        current.clear()
        current_truncated = False
        in_printable_run = False

    with path.open("rb") as stream:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            if not head:
                head = chunk[:64]
            tail = (tail + chunk)[-64:]
            sha.update(chunk)
            counts.update(chunk)

            scan = previous + chunk
            scan_base = offset - len(previous)
            for name, marker in MARKERS.items():
                start = 0
                while True:
                    found = scan.find(marker, start)
                    if found < 0:
                        break
                    absolute = scan_base + found
                    if absolute >= 0 and (
                        not marker_offsets[name] or marker_offsets[name][-1] != absolute
                    ):
                        marker_offsets[name].append(absolute)
                    start = found + 1
            previous = scan[-overlap:] if overlap else b""

            if len(strings) < max_strings:
                for index, byte in enumerate(chunk):
                    absolute = offset + index
                    if 32 <= byte <= 126 or byte == 9:
                        if not in_printable_run:
                            current_start = absolute
                            in_printable_run = True
                        if len(current) < max_string_length:
                            current.append(byte)
                        else:
                            current_truncated = True
                    else:
                        finish_string()
                        if len(strings) >= max_strings:
                            break
            else:
                current.clear()
                current_truncated = False
                in_printable_run = False
            offset += len(chunk)

    if len(strings) < max_strings:
        finish_string()

    markers = {name: offsets for name, offsets in marker_offsets.items() if offsets}
    classifications = []
    if marker_offsets["elf"] and marker_offsets["elf"][0] == 0:
        classifications.append("ELF executable/shared-object candidate")
    if marker_offsets["qnx_startup"]:
        classifications.append("contains QNX startup-header marker")
    if marker_offsets["imagefs"]:
        classifications.append("contains ImageFS marker")
    if marker_offsets["lzoz"] and marker_offsets["lzoz"][0] == 0:
        classifications.append("MHI2 LZOZ container candidate")
    if marker_offsets["qssl_f3s"]:
        classifications.append("contains QNX EFS/QSSL_F3S marker")
    if all(marker_offsets[name] for name in ("android_boot", "kernel_primary", "kernel_recovery")):
        classifications.append("quickboot boot-selection-loader candidate")

    return {
        "source": path.name,
        "bytes": size,
        "sha256": sha.hexdigest(),
        "entropy_bits_per_byte": round(entropy_from_counts(counts, size), 6),
        "head_hex": head.hex(),
        "tail_hex": tail.hex(),
        "markers": markers,
        "classifications": classifications,
        "strings": strings,
        "string_capture": {
            "max_strings": max_strings,
            "min_length": min_string,
            "max_length": max_string_length,
        },
        "evidence_limit": "Static read-only analysis only; markers do not prove runtime role or execution flow.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("--max-strings", type=int, default=128)
    parser.add_argument("--min-string", type=int, default=5)
    parser.add_argument("--max-string-length", type=int, default=4096)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source = args.binary.resolve(strict=True)
    report = analyze_binary(
        source,
        max_strings=args.max_strings,
        min_string=args.min_string,
        max_string_length=args.max_string_length,
    )
    rendered = json.dumps(report, indent=2)
    print(rendered)
    if args.output:
        if args.output.exists():
            raise FileExistsError(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
