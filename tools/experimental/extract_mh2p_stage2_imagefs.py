# SPDX-License-Identifier: GPL-3.0-only
#!/usr/bin/env python3
"""Validate and extract the first ImageFS found in an MH2P LZ4_ stage2 image.

This is deliberately a partial probe, not a full LZ4_ container decoder. It
decodes one bounded raw LZ4 block from the observed 0x2000 payload offset,
cross-checks it with python-lz4, and materializes the leading ImageFS only.
All following container bytes remain unclassified and are retained as such.
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


OBSERVED_DATA_OFFSET = 0x2000
MAX_BLOCK_LIMIT = 32 * 1024 * 1024
MAX_MATCH_OVERSHOOT = 64 * 1024


def lz4_compress_bound(uncompressed_size: int) -> int:
    """Return the standard worst-case encoded-size bound for one LZ4 block."""
    if uncompressed_size < 0:
        raise ValueError("uncompressed size must be non-negative")
    return uncompressed_size + (uncompressed_size // 255) + 16


def read_bounded_compressed_input(source: Path, output_limit: int) -> bytes:
    """Read only the maximum compressed prefix needed by the bounded probe.

    The pure-Python decoder permits at most MAX_MATCH_OVERSHOOT bytes beyond
    the advertised output target.  Use the LZ4 worst-case encoded-size bound
    for that maximum decoded allowance instead of buffering the rest of the
    source file.
    """
    if output_limit <= 0 or output_limit > MAX_BLOCK_LIMIT:
        raise ValueError(f"unsafe LZ4 output limit: {output_limit}")
    max_decoded = output_limit + MAX_MATCH_OVERSHOOT
    max_encoded = lz4_compress_bound(max_decoded)
    with source.open("rb") as stream:
        stream.seek(OBSERVED_DATA_OFFSET)
        return stream.read(max_encoded)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def decode_lz4_block_to_limit(data: bytes, output_limit: int) -> tuple[int, bytes]:
    """Decode raw LZ4 sequences until output reaches the advertised block cap.

    The returned input prefix is subsequently validated by python-lz4. The
    pure-Python pass is only used to discover a bounded candidate prefix; it
    is not considered authoritative on its own.
    """
    if output_limit <= 0 or output_limit > MAX_BLOCK_LIMIT:
        raise ValueError(f"unsafe LZ4 output limit: {output_limit}")
    input_pos = 0
    output = bytearray()
    hard_limit = output_limit + MAX_MATCH_OVERSHOOT

    while len(output) < output_limit:
        if input_pos >= len(data):
            raise ValueError("truncated LZ4 block before output limit")
        token = data[input_pos]
        input_pos += 1

        literal_length = token >> 4
        if literal_length == 15:
            while True:
                if input_pos >= len(data):
                    raise ValueError("truncated LZ4 literal-length extension")
                extra = data[input_pos]
                input_pos += 1
                literal_length += extra
                if extra != 255:
                    break

        if input_pos + literal_length > len(data):
            raise ValueError("LZ4 literal extends beyond source bounds")
        if len(output) + literal_length > hard_limit:
            raise ValueError("LZ4 literal exceeds bounded output allowance")
        output.extend(data[input_pos:input_pos + literal_length])
        input_pos += literal_length
        if len(output) >= output_limit:
            break

        if input_pos + 2 > len(data):
            raise ValueError("truncated LZ4 match offset")
        offset = data[input_pos] | (data[input_pos + 1] << 8)
        input_pos += 2
        if offset == 0 or offset > len(output):
            raise ValueError(f"invalid LZ4 match offset {offset} at output {len(output)}")

        match_length = token & 0x0F
        if match_length == 15:
            while True:
                if input_pos >= len(data):
                    raise ValueError("truncated LZ4 match-length extension")
                extra = data[input_pos]
                input_pos += 1
                match_length += extra
                if extra != 255:
                    break
        match_length += 4
        if len(output) + match_length > hard_limit:
            raise ValueError("LZ4 match exceeds bounded output allowance")
        for _ in range(match_length):
            output.append(output[-offset])

    return input_pos, bytes(output)


def load_readers() -> tuple[Any, Any]:
    tools_dir = Path(__file__).resolve().parents[1]
    if str(tools_dir) not in sys.path:
        sys.path.insert(0, str(tools_dir))
    from imagefs import inventory_imagefs, materialize_imagefs
    return inventory_imagefs, materialize_imagefs


def run(args: argparse.Namespace) -> dict[str, Any]:
    source = args.source.resolve(strict=True)
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError(f"refusing to reuse existing output: {output}")

    source_hash = sha256_file(source)
    if args.expected_sha256 and source_hash.casefold() != args.expected_sha256.casefold():
        raise ValueError(f"source SHA-256 mismatch: {source_hash}")
    with source.open("rb") as stream:
        header = stream.read(OBSERVED_DATA_OFFSET)
    if len(header) != OBSERVED_DATA_OFFSET or header[:4] != b"LZ4_":
        raise ValueError("expected the observed MH2P LZ4_ header")
    block_limit = int.from_bytes(header[4:8], "little")
    if not 0 < block_limit <= MAX_BLOCK_LIMIT:
        raise ValueError(f"unsafe LZ4 block cap in header: {block_limit}")

    compressed_prefix = read_bounded_compressed_input(source, block_limit)
    compressed_bytes, decoded_block = decode_lz4_block_to_limit(compressed_prefix, block_limit)
    encoded_block = compressed_prefix[:compressed_bytes]

    if args.lz4_module_root:
        sys.path.insert(0, str(args.lz4_module_root.resolve(strict=True)))
    try:
        import lz4.block
    except ModuleNotFoundError as exc:
        raise RuntimeError("python-lz4 is required; pass --lz4-module-root") from exc
    official_decoded = lz4.block.decompress(
        encoded_block, uncompressed_size=len(decoded_block)
    )
    if official_decoded != decoded_block:
        raise ValueError("independent LZ4 decoder disagrees with bounded probe")

    if decoded_block[:7] != b"imagefs":
        raise ValueError("validated LZ4 output does not begin with ImageFS")
    endian = ">" if decoded_block[7] & 0x01 else "<"
    imagefs_size = int.from_bytes(decoded_block[8:12], "big" if endian == ">" else "little")
    if imagefs_size < 92 or imagefs_size > len(decoded_block):
        raise ValueError(f"invalid embedded ImageFS size: {imagefs_size}")
    imagefs_bytes = decoded_block[:imagefs_size]

    inventory_imagefs, materialize_imagefs = load_readers()
    with tempfile.TemporaryDirectory(prefix="mh2p-stage2-imagefs-check-") as temporary:
        validation_image = Path(temporary) / "candidate.imagefs"
        validation_image.write_bytes(imagefs_bytes)
        inventory = inventory_imagefs(validation_image)

    if output.exists():
        raise FileExistsError(f"output appeared during validation: {output}")
    output.mkdir(parents=True, exist_ok=False)
    try:
        decoded_path = output / "first-lz4-block.decoded"
        imagefs_path = output / "main_stage2.imagefs"
        decoded_path.write_bytes(decoded_block)
        imagefs_path.write_bytes(imagefs_bytes)
        materialized = materialize_imagefs(
            imagefs_path, output / "files", output / "imagefs-metadata.json"
        )
        manifest = {
            "status": "PARTIAL_FIRST_BLOCK_ONLY",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "source": str(source),
            "source_bytes": source.stat().st_size,
            "source_sha256": source_hash,
            "source_class": "LOCAL-ONLY; read-only",
            "container_magic": "LZ4_",
            "observed_payload_offset": OBSERVED_DATA_OFFSET,
            "header_block_limit": block_limit,
            "validated_compressed_prefix_bytes": compressed_bytes,
            "validated_compressed_prefix_sha256": sha256_bytes(encoded_block),
            "decoded_prefix_bytes": len(decoded_block),
            "decoded_prefix_sha256": sha256_bytes(decoded_block),
            "official_lz4_crosscheck": "PASS; python-lz4 output byte-identical",
            "embedded_imagefs_bytes": imagefs_size,
            "embedded_imagefs_sha256": sha256_bytes(imagefs_bytes),
            "imagefs_inventory": {
                "entries": len(inventory["entries"]),
                "duplicate_paths": len(inventory["duplicate_paths"]),
                "types": {kind: sum(row["type"] == kind for row in inventory["entries"])
                          for kind in ("file", "directory", "symlink", "special")},
            },
            "materialized": materialized,
            "unexamined_source_bytes_after_candidate_prefix": (
                source.stat().st_size - OBSERVED_DATA_OFFSET - compressed_bytes
            ),
            "scope_limit": "No claim that the rest of the MH2P LZ4_ container has been decoded.",
        }
        with (output / "manifest.json").open("x", encoding="utf-8") as stream:
            json.dump(manifest, stream, indent=2)
        return manifest
    except BaseException as exc:
        with (output / "FREEZE_LEDGER.md").open("x", encoding="utf-8") as stream:
            stream.write(f"# MH2P stage2 probe freeze\n\nSource: {source}\n\n"
                         f"Target: {output}\n\nFailure: {type(exc).__name__}: {exc}\n\n"
                         "Partial output retained; no cleanup attempted.\n")
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
