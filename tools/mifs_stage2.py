# SPDX-License-Identifier: GPL-3.0-only
"""Safe reader for the LZOZ block wrapper used by MHI2 MMX MIFS stage 2."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import struct
from typing import BinaryIO, Callable


HEADER_BYTES = 0x200
PAYLOAD_OFFSET = 0x800
ALIGNMENT = 0x200
DEFAULT_MAX_BLOCK_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_OUTPUT_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(frozen=True)
class Block:
    offset: int
    compressed_bytes: int


@dataclass(frozen=True)
class Container:
    declared_block_bytes: int
    blocks: tuple[Block, ...]
    compressed_bytes: int
    payload_end: int


def parse_container(
    stream: BinaryIO,
    source_bytes: int,
    *,
    max_block_bytes: int = DEFAULT_MAX_BLOCK_BYTES,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> Container:
    """Validate block table and payload bounds without decompressing data."""
    if source_bytes < PAYLOAD_OFFSET:
        raise ValueError("LZOZ image is shorter than its header and initial payload offset")
    stream.seek(0)
    header = stream.read(HEADER_BYTES)
    if len(header) != HEADER_BYTES or header[:4] != b"LZOZ":
        raise ValueError("missing or truncated LZOZ header")
    declared_block_bytes = struct.unpack_from("<I", header, 4)[0]
    if not 0 < declared_block_bytes <= max_block_bytes:
        raise ValueError(f"unsafe LZOZ output block size: {declared_block_bytes}")

    blocks: list[Block] = []
    compressed_total = 0
    cursor = PAYLOAD_OFFSET
    table_end = False
    for table_offset in range(8, HEADER_BYTES, 4):
        compressed = struct.unpack_from("<I", header, table_offset)[0]
        if compressed == 0:
            table_end = True
            break
        if compressed > source_bytes or cursor + compressed > source_bytes:
            raise ValueError(f"LZOZ block at 0x{cursor:x} extends beyond source image")
        blocks.append(Block(cursor, compressed))
        compressed_total += compressed
        if len(blocks) * declared_block_bytes > max_output_bytes:
            raise ValueError("LZOZ output exceeds configured total size limit")
        # Advance to the next 0x200-byte boundary; aligned blocks stay aligned.
        cursor += ((compressed + ALIGNMENT - 1) // ALIGNMENT) * ALIGNMENT
    if not table_end:
        raise ValueError("LZOZ block table has no zero terminator")
    if not blocks:
        raise ValueError("LZOZ image contains no data blocks")
    return Container(declared_block_bytes, tuple(blocks), compressed_total, cursor)


def decompress_container(
    source: Path,
    destination: Path,
    *,
    decompress: Callable[[bytes, int], bytes],
    max_block_bytes: int = DEFAULT_MAX_BLOCK_BYTES,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
) -> dict[str, int | str]:
    """Decode to a new file; never overwrite a prior artifact."""
    source_bytes = source.stat().st_size
    container: Container
    total_output = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    with source.open("rb") as source_stream:
        container = parse_container(source_stream, source_bytes,
                                    max_block_bytes=max_block_bytes,
                                    max_output_bytes=max_output_bytes)
        with destination.open("xb") as output_stream:
            for index, block in enumerate(container.blocks):
                source_stream.seek(block.offset)
                compressed = source_stream.read(block.compressed_bytes)
                if len(compressed) != block.compressed_bytes:
                    raise IOError(f"truncated LZOZ block {index}")
                expanded = decompress(compressed, container.declared_block_bytes)
                if not expanded or len(expanded) > container.declared_block_bytes:
                    raise ValueError(f"invalid expanded length for LZOZ block {index}: {len(expanded)}")
                if index < len(container.blocks) - 1 and len(expanded) != container.declared_block_bytes:
                    raise ValueError(f"short non-final LZOZ block {index}: {len(expanded)}")
                total_output += len(expanded)
                if total_output > max_output_bytes:
                    raise ValueError("LZOZ output exceeds configured total size limit")
                output_stream.write(expanded)
    return {"output": destination.name, "blocks": len(container.blocks),
            "declared_block_bytes": container.declared_block_bytes,
            "compressed_payload_bytes": container.compressed_bytes,
            "decompressed_bytes": total_output,
            "payload_end": container.payload_end}
