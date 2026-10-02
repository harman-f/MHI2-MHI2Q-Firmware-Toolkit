# SPDX-License-Identifier: GPL-3.0-only
"""Minimal, bounds-checked QNX IFS startup parser for UCL/NVR2B images."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import struct

from ucl_nrv2b import decompress_nrv2b


STARTUP = struct.Struct("<LHBBHHLLLLLLLLLH6sL")
STARTUP_MAGIC = bytes.fromhex("EB7EFF00")
MAX_IMAGEFS_BYTES = 256 * 1024 * 1024
MAX_BLOCK_BYTES = 64 * 1024
SCAN_CHUNK_BYTES = 1024 * 1024


@dataclass(frozen=True)
class StartupHeader:
    offset: int
    version: int
    flags1: int
    flags2: int
    header_size: int
    machine: int
    startup_size: int
    stored_size: int
    imagefs_size: int
    preboot_size: int
    compression_type: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_startup_headers(source: Path, source_size: int) -> list[tuple[int, tuple]]:
    """Find structurally plausible startup headers without fixed image offsets."""
    candidates: dict[int, tuple] = {}
    overlap = b""
    consumed = 0
    with source.open("rb") as stream:
        while chunk := stream.read(SCAN_CHUNK_BYTES):
            searchable = overlap + chunk
            searchable_offset = consumed - len(overlap)
            cursor = 0
            while (relative := searchable.find(STARTUP_MAGIC, cursor)) >= 0:
                offset = searchable_offset + relative
                cursor = relative + 1
                # Signatures in the carried overlap were already considered.
                if offset < consumed or offset + STARTUP.size > source_size:
                    continue
                stream.seek(offset)
                raw = stream.read(STARTUP.size)
                if len(raw) != STARTUP.size:
                    continue
                fields = STARTUP.unpack(raw)
                stored_size = fields[12]
                if (fields[0] != int.from_bytes(STARTUP_MAGIC, "little")
                        or fields[4] < STARTUP.size
                        or fields[11] < fields[4]
                        or stored_size < fields[11]
                        or offset + stored_size > source_size
                        or not 0 < fields[14] <= MAX_IMAGEFS_BYTES):
                    continue
                candidates[offset] = fields
            stream.seek(consumed + len(chunk))
            consumed += len(chunk)
            overlap = searchable[-(len(STARTUP_MAGIC) - 1):]
    return sorted(candidates.items())


def decompress_ucl_ifs(source: Path, destination: Path) -> dict[str, object]:
    """Decode a QNX IFS containing UCL/NRV2B length-prefixed blocks."""
    source_size = source.stat().st_size
    candidates = find_startup_headers(source, source_size)
    if not candidates:
        raise ValueError("no structurally valid QNX startup header (EB7EFF00) found in source")
    if len(candidates) != 1:
        offsets = ", ".join(f"0x{offset:x}" for offset, _ in candidates)
        raise ValueError(f"multiple structurally valid QNX startup headers; refusing ambiguous image: {offsets}")
    offset, fields = candidates[0]
    (signature, version, flags1, flags2, header_size, machine, startup_vaddr,
     paddr_bias, image_paddr, ram_paddr, ram_size, startup_size, stored_size,
     imagefs_paddr, imagefs_size, preboot_size, _reserved, addr_off) = fields
    if signature != int.from_bytes(STARTUP_MAGIC, "little"):
        raise ValueError("invalid QNX startup header signature")
    compression_type = (flags1 >> 2) & 0x7
    if compression_type != 3:
        raise ValueError(f"QNX IFS is not UCL-compressed (type={compression_type})")
    if header_size < STARTUP.size or startup_size < header_size:
        raise ValueError("invalid QNX startup header/payload sizes")
    if stored_size < startup_size or offset + stored_size > source_size:
        raise ValueError("QNX stored image extends beyond source file")
    if not 0 < imagefs_size <= MAX_IMAGEFS_BYTES:
        raise ValueError(f"unsafe QNX ImageFS size: {imagefs_size}")

    payload_start = offset + startup_size
    payload_end = offset + stored_size
    output_bytes = 0
    block_count = 0
    compressed_bytes = 0
    digest = hashlib.sha256()
    trailer = b""
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as input_stream, destination.open("xb") as output_stream:
        input_stream.seek(payload_start)
        while input_stream.tell() + 2 <= payload_end:
            length_bytes = input_stream.read(2)
            if len(length_bytes) != 2:
                raise IOError("truncated QNX UCL block length")
            compressed_size = int.from_bytes(length_bytes, "big")
            if compressed_size == 0:
                trailer = input_stream.read(payload_end - input_stream.tell())
                break
            if compressed_size > 65535 or input_stream.tell() + compressed_size > payload_end:
                raise ValueError("QNX UCL block extends beyond stored image")
            if output_bytes >= imagefs_size:
                raise ValueError("extra QNX UCL block after declared ImageFS length")
            compressed = input_stream.read(compressed_size)
            if len(compressed) != compressed_size:
                raise IOError("truncated QNX UCL block payload")
            expected = min(MAX_BLOCK_BYTES, imagefs_size - output_bytes)
            expanded = decompress_nrv2b(compressed, max_output_bytes=expected)
            if len(expanded) != expected:
                raise ValueError(f"wrong QNX UCL block output length: {len(expanded)} != {expected}")
            output_stream.write(expanded)
            digest.update(expanded)
            output_bytes += len(expanded)
            compressed_bytes += compressed_size
            block_count += 1
        else:
            raise ValueError("QNX UCL block list has no zero terminator")

    if block_count == 0 or output_bytes != imagefs_size:
        raise ValueError(f"QNX UCL output length mismatch: {output_bytes} != {imagefs_size}")
    if any(trailer):
        # Preserve but do not interpret a format-specific trailer/check value.
        trailer_hex = trailer.hex()
    else:
        trailer_hex = trailer.hex()

    startup = StartupHeader(offset, version, flags1, flags2, header_size,
                            machine, startup_size, stored_size, imagefs_size,
                            preboot_size, compression_type)
    return {"source_bytes": source_size, "source_sha256": sha256_file(source),
            "startup_header": asdict(startup), "output_bytes": output_bytes,
            "output_sha256": digest.hexdigest(), "blocks": block_count,
            "compressed_block_bytes": compressed_bytes,
            "trailing_bytes_hex": trailer_hex,
            "output": destination.name}
