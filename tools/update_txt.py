#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
"""Audit/refresh the integrity fields of an existing Harman MHI2 update.txt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import zlib

CRC_RE = re.compile(r'^(\s*CRC\s*=\s*)([^\r\n]*)(\r?\n)?$', re.I)
META_RE = re.compile(r'^(\s*MetafileCRC\s*=\s*)([^\r\n]*)(\r?\n)?$', re.I)
METAINFO_HASH_RE = re.compile(r'^\s*MetafileChecksum\s*=\s*"([0-9a-fA-F]{40})"\s*$', re.I)
SKIP_META_RE = re.compile(r'^\s*skipMetaCRC\s*=\s*"true"\s*$', re.I)


def read_preserved(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return stream.read()


def write_preserved(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(text)


def metainfo_crc_value(text: str) -> str:
    checksum = None
    skip = False
    for line in text.splitlines():
        match = METAINFO_HASH_RE.match(line)
        if match:
            checksum = match.group(1).lower()
        if SKIP_META_RE.match(line):
            skip = True
    if checksum:
        return checksum
    if skip:
        return "skip"
    raise ValueError("metainfo2 has neither MetafileChecksum nor skipMetaCRC=true")


def crc_without_crc_line(text: str) -> str:
    payload = "".join(line for line in text.splitlines(keepends=True) if not CRC_RE.match(line))
    return f"{zlib.crc32(payload.encode('utf-8')) & 0xffffffff:08x}"


def refresh(update_text: str, metainfo_text: str) -> tuple[str, dict]:
    lines = update_text.splitlines(keepends=True)
    meta_value = metainfo_crc_value(metainfo_text)
    changes = []
    meta_found = False
    for index, line in enumerate(lines):
        match = META_RE.match(line)
        if match:
            meta_found = True
            old = match.group(2).strip()
            if old != meta_value:
                ending = match.group(3) or ""
                lines[index] = f"{match.group(1)}{meta_value}{ending}"
                changes.append({"line": index + 1, "key": "MetafileCRC", "old": old, "new": meta_value})
    if not meta_found:
        raise ValueError("update.txt has no MetafileCRC line; refusing to invent transaction structure")

    interim = "".join(lines)
    expected_crc = crc_without_crc_line(interim)
    crc_found = False
    for index, line in enumerate(lines):
        match = CRC_RE.match(line)
        if match:
            crc_found = True
            old = match.group(2).strip()
            if old.lower() != expected_crc:
                ending = match.group(3) or ""
                lines[index] = f"{match.group(1)}{expected_crc}{ending}"
                changes.append({"line": index + 1, "key": "CRC", "old": old, "new": expected_crc})
    if not crc_found:
        raise ValueError("update.txt has no CRC line; refusing to invent transaction structure")

    result = "".join(lines)
    return result, {"status": "PASS", "changes": changes,
                    "MetafileCRC": meta_value, "CRC": crc_without_crc_line(result)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("update", type=Path)
    parser.add_argument("--metainfo", type=Path, required=True)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.write and args.output:
        parser.error("--write and --output are mutually exclusive")

    update = args.update.resolve(strict=True)
    metainfo = args.metainfo.resolve(strict=True)
    result, report = refresh(read_preserved(update), read_preserved(metainfo))
    print(json.dumps(report, indent=2))
    if args.write:
        write_preserved(update, result)
    elif args.output:
        if args.output.exists():
            raise FileExistsError(args.output)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_preserved(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
