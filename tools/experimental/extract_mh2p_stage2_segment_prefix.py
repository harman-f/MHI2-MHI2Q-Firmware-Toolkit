# SPDX-License-Identifier: GPL-3.0-only
#!/usr/bin/env python3
"""Decode the validated, sector-aligned LZ4 segment prefix in MH2P stage2.

The observed LZ4_ file has a little-endian size table at offset 8. This tool
only follows entries that fit the source, validates full LZ4 input consumption
and 512-byte 0xff padding, caps every decoded segment at the advertised block
limit, and uses python-lz4 for decompression. It scans the concatenated output
for complete ImageFS images and materializes them with the reviewed bounded
ImageFS reader. For incomplete images with a complete directory, only file
extents fully inside the decoded prefix are materialized.

This is deliberately not a full container decoder: the observed table has
entries that do not fit the remaining source, and the trailing bytes remain
unclassified. Output directories can contain device-specific SSH host-key
files; keep generated trees LOCAL-ONLY and do not commit them.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from typing import Any


HEADER_SIZE = 0x2000
SIZE_TABLE_OFFSET = 8
MAX_TABLE_ENTRIES = 4096
ALIGNMENT = 512
MAX_BLOCK_LIMIT = 32 * 1024 * 1024
MAX_TOTAL_DECODED = 512 * 1024 * 1024
SENSITIVE_PATH_HINTS = (
    "ssh_host_", "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519",
    "authorized_keys", "known_hosts", "privatekey", "private_key",
)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def align_up(value: int, alignment: int = ALIGNMENT) -> int:
    if alignment <= 0 or alignment & (alignment - 1):
        raise ValueError("alignment must be a positive power of two")
    return (value + alignment - 1) & ~(alignment - 1)


def parse_header(header: bytes) -> tuple[int, list[int]]:
    if len(header) != HEADER_SIZE or header[:4] != b"LZ4_":
        raise ValueError("expected the observed 0x2000-byte LZ4_ header")
    block_limit = int.from_bytes(header[4:8], "little")
    if not 0 < block_limit <= MAX_BLOCK_LIMIT:
        raise ValueError(f"unsafe advertised LZ4 block limit: {block_limit}")
    sizes: list[int] = []
    position = SIZE_TABLE_OFFSET
    while position + 4 <= len(header) and len(sizes) < MAX_TABLE_ENTRIES:
        size = int.from_bytes(header[position:position + 4], "little")
        if size == 0:
            break
        sizes.append(size)
        position += 4
    if not sizes:
        raise ValueError("empty LZ4 segment-size table")
    return block_limit, sizes


def audit_lz4_block(encoded: bytes, output_limit: int) -> tuple[int, int]:
    """Require a complete raw LZ4 block, consuming every encoded byte.

    python-lz4 returns decoded bytes but does not expose how much input it
    consumed. This length-only parser independently checks sequence bounds,
    back-reference offsets, and the final literal-only sequence.
    """
    position = 0
    output_size = 0
    sequences = 0

    def extended_length(initial: int) -> int:
        nonlocal position
        length = initial
        if initial == 15:
            while True:
                if position >= len(encoded):
                    raise ValueError("truncated LZ4 length extension")
                extra = encoded[position]
                position += 1
                length += extra
                if extra != 255:
                    break
        return length

    while position < len(encoded):
        token = encoded[position]
        position += 1
        sequences += 1
        literals = extended_length(token >> 4)
        if literals > len(encoded) - position:
            raise ValueError("truncated LZ4 literals")
        position += literals
        output_size += literals
        if output_size > output_limit:
            raise ValueError("LZ4 output exceeds advertised block limit")
        if position == len(encoded):
            return output_size, sequences
        if len(encoded) - position < 2:
            raise ValueError("truncated LZ4 match offset")
        offset = int.from_bytes(encoded[position:position + 2], "little")
        position += 2
        if not 0 < offset <= output_size:
            raise ValueError("invalid LZ4 match offset")
        output_size += extended_length(token & 15) + 4
        if output_size > output_limit:
            raise ValueError("LZ4 output exceeds advertised block limit")
    raise ValueError("LZ4 block lacks a final literal sequence")


def load_readers() -> tuple[Any, Any, Any]:
    tools_dir = Path(__file__).resolve().parents[1]
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from imagefs import inventory_imagefs, materialize_imagefs, materialize_imagefs_prefix
    return inventory_imagefs, materialize_imagefs, materialize_imagefs_prefix


def _sensitive_path_hints(entries: list[dict[str, Any]]) -> list[str]:
    found = set()
    for row in entries:
        path = row.get("path", "").casefold()
        if any(hint in path for hint in SENSITIVE_PATH_HINTS):
            found.add(row["path"])
    return sorted(found)


def run(args: argparse.Namespace) -> dict[str, Any]:
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to reuse existing output: {output}")
    source_hash = sha256_file(source)
    if args.expected_sha256 and source_hash.casefold() != args.expected_sha256.casefold():
        raise ValueError(f"source SHA-256 mismatch: {source_hash}")
    with source.open("rb") as stream:
        header = stream.read(HEADER_SIZE)
    block_limit, sizes = parse_header(header)
    inventory_imagefs, materialize_imagefs, materialize_imagefs_prefix = load_readers()

    segment_rows: list[dict[str, Any]] = []
    decoded_parts: list[bytes] = []
    cursor = HEADER_SIZE
    decoded_total = 0
    stop_reason: str | None = None
    import_root = args.lz4_module_root.resolve(strict=True) if args.lz4_module_root else None
    if import_root:
        sys.path.insert(0, str(import_root))
    try:
        import lz4.block
    except ModuleNotFoundError as exc:
        raise RuntimeError("python-lz4 is required; pass --lz4-module-root") from exc

    for index, compressed_size in enumerate(sizes):
        remaining = source.stat().st_size - cursor
        if compressed_size > remaining:
            stop_reason = (
                f"table entry {index} declares {compressed_size} bytes, "
                f"but only {remaining} source bytes remain at {cursor:#x}"
            )
            break
        with source.open("rb") as stream:
            stream.seek(cursor)
            encoded = stream.read(compressed_size)
        if len(encoded) != compressed_size:
            stop_reason = f"short source read for segment {index} at {cursor:#x}"
            break
        audited_bytes, lz4_sequences = audit_lz4_block(encoded, block_limit)
        decoded = lz4.block.decompress(encoded, uncompressed_size=block_limit + 1)
        if not decoded:
            raise ValueError(f"empty decoded segment {index}")
        if len(decoded) > block_limit:
            raise ValueError(
                f"segment {index} exceeds advertised block limit: {len(decoded)} > {block_limit}"
            )
        if len(decoded) != audited_bytes:
            raise ValueError(
                f"segment {index} LZ4 audit/output disagreement: "
                f"{audited_bytes} != {len(decoded)}"
            )
        decoded_total += len(decoded)
        if decoded_total > MAX_TOTAL_DECODED:
            raise ValueError("decoded output exceeds the total safety bound")
        segment_rows.append({
            "index": index,
            "source_offset": cursor,
            "compressed_bytes": compressed_size,
            "compressed_sha256": sha256_bytes(encoded),
            "decoded_offset": decoded_total - len(decoded),
            "decoded_bytes": len(decoded),
            "decoded_sha256": sha256_bytes(decoded),
            "lz4_sequences": lz4_sequences,
        })
        decoded_parts.append(decoded)
        end = cursor + compressed_size
        next_cursor = align_up(end)
        with source.open("rb") as stream:
            stream.seek(end)
            padding = stream.read(next_cursor - end)
        if len(padding) != next_cursor - end or any(value != 0xFF for value in padding):
            raise ValueError(f"non-0xff or truncated sector padding after segment {index}")
        cursor = next_cursor
    else:
        stop_reason = "all nonzero size-table entries fit and decoded"

    decoded_stream = b"".join(decoded_parts)
    if not decoded_stream:
        raise ValueError("no LZ4 segments decoded")

    output.mkdir(parents=True, exist_ok=False)
    try:
        decoded_path = output / "decoded-segment-prefix.bin"
        decoded_path.write_bytes(decoded_stream)
        imagefs_root = output / "imagefs"
        imagefs_root.mkdir()
        candidates: list[dict[str, Any]] = []
        search_from = 0
        ordinal = 0
        while True:
            offset = decoded_stream.find(b"imagefs", search_from)
            if offset < 0:
                break
            search_from = offset + 1
            row: dict[str, Any] = {"offset": offset}
            if offset + 12 > len(decoded_stream):
                row.update(status="INCOMPLETE_HEADER")
                candidates.append(row)
                continue
            flags = decoded_stream[offset + 7]
            endian = "big" if flags & 0x01 else "little"
            declared_size = int.from_bytes(decoded_stream[offset + 8:offset + 12], endian)
            row.update(flags=flags, byte_order=endian, declared_bytes=declared_size,
                       available_bytes=len(decoded_stream) - offset)
            if declared_size < 92:
                row.update(status="REJECTED_INVALID_SIZE")
                candidates.append(row)
                continue
            if declared_size > len(decoded_stream) - offset:
                ordinal += 1
                image_dir = imagefs_root / f"imagefs-{ordinal:02d}"
                image_dir.mkdir()
                image_path = image_dir / "imagefs.prefix.bin"
                image_path.write_bytes(decoded_stream[offset:])
                try:
                    inventory = inventory_imagefs(image_path, allow_incomplete=True)
                    materialized = materialize_imagefs_prefix(
                        image_path, image_dir / "files", image_dir / "metadata.json"
                    )
                except Exception as exc:
                    row.update(status="INCOMPLETE_IMAGEFS_UNVALIDATED_DIRECTORY",
                               error=f"{type(exc).__name__}: {exc}")
                    candidates.append(row)
                    continue
                row.update(
                    status="INCOMPLETE_IMAGEFS_VALID_DIRECTORY",
                    prefix_sha256=sha256_file(image_path),
                    entries=len(inventory["entries"]),
                    complete_file_entries=inventory["complete_file_entries"],
                    incomplete_file_entries=inventory["incomplete_file_entries"],
                    sensitive_path_hints=_sensitive_path_hints(inventory["entries"]),
                    local_output=str(image_dir), materialized=materialized,
                )
                candidates.append(row)
                continue

            ordinal += 1
            image_dir = imagefs_root / f"imagefs-{ordinal:02d}"
            image_dir.mkdir()
            image_path = image_dir / "imagefs.img"
            image_path.write_bytes(decoded_stream[offset:offset + declared_size])
            try:
                inventory = inventory_imagefs(image_path)
            except Exception as exc:
                row.update(status="REJECTED_IMAGEFS_INVENTORY", error=f"{type(exc).__name__}: {exc}")
                candidates.append(row)
                continue
            materialized = materialize_imagefs(
                image_path, image_dir / "files", image_dir / "metadata.json"
            )
            entries = inventory["entries"]
            row.update(
                status="VALID_IMAGEFS",
                sha256=sha256_file(image_path),
                entries=len(entries),
                duplicate_paths=len(inventory["duplicate_paths"]),
                file_entries=sum(entry["type"] == "file" for entry in entries),
                directory_entries=sum(entry["type"] == "directory" for entry in entries),
                symlink_entries=sum(entry["type"] == "symlink" for entry in entries),
                sensitive_path_hints=_sensitive_path_hints(entries),
                local_output=str(image_dir),
                materialized=materialized,
            )
            candidates.append(row)

        manifest = {
            "status": "PARTIAL_VALIDATED_SEGMENT_PREFIX",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "source": str(source),
            "source_bytes": source.stat().st_size,
            "source_sha256": source_hash,
            "source_class": "LOCAL-ONLY; read-only",
            "container_magic": "LZ4_",
            "header_bytes": HEADER_SIZE,
            "advertised_block_limit": block_limit,
            "size_table_entries": len(sizes),
            "alignment_bytes": ALIGNMENT,
            "decoded_segment_count": len(segment_rows),
            "decoded_segment_bytes": decoded_total,
            "decoded_stream_sha256": sha256_bytes(decoded_stream),
            "next_source_offset": cursor,
            "unexamined_source_bytes": source.stat().st_size - cursor,
            "stop_reason": stop_reason,
            "segments": segment_rows,
            "imagefs_candidates": candidates,
            "scope_limit": (
                "Only in-bounds size-table entries with fully consumed valid LZ4 data and "
                "0xff sector padding were decoded. Incomplete ImageFS directories may be "
                "inventoried, but only files fully within that validated prefix are materialized. "
                "Remaining source bytes and table semantics beyond this prefix are unresolved. "
                "Output may contain device-specific SSH host keys; keep LOCAL-ONLY."
            ),
        }
        with (output / "manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
        return manifest
    except BaseException as exc:
        with (output / "FREEZE_LEDGER.md").open("x", encoding="utf-8") as stream:
            stream.write(
                f"# MH2P stage2 segment-prefix freeze\n\nSource: {source}\n\n"
                f"Target: {output}\n\nFailure: {type(exc).__name__}: {exc}\n\n"
                "Partial output retained; no cleanup attempted.\n"
            )
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True,
                        help="new local output directory")
    parser.add_argument("--lz4-module-root", type=Path,
                        help="optional Python site-packages root containing lz4")
    parser.add_argument("--expected-sha256")
    try:
        result = run(parser.parse_args())
        print(json.dumps(result, indent=2), flush=True)
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
