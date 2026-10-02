# SPDX-License-Identifier: GPL-3.0-only
"""Bounded parser for MHI2's Android-style, zlib-wrapped QNX image modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
import struct
import zlib


MAGIC = b"A\xffD\xffO\xffD\xff"
ANDROID_HEADER = struct.Struct("<8I")
QNX_STARTUP = struct.Struct("<LHBBHHLLLLLLLLLH6sL")
QNX_SIGNATURE = bytes.fromhex("EB7EFF00")
IMAGEFS_SIGNATURE = b"imagefs"
MAX_COMPRESSED_BYTES = 512 * 1024 * 1024
MAX_DECOMPRESSED_BYTES = 256 * 1024 * 1024


@dataclass(frozen=True)
class QnxStartup:
    offset: int
    version: int
    flags1: int
    flags2: int
    header_size: int
    machine: int
    startup_vaddr: int
    paddr_bias: int
    image_paddr: int
    ram_paddr: int
    ram_size: int
    startup_size: int
    stored_size: int
    imagefs_paddr: int
    imagefs_size: int
    preboot_size: int
    addr_off: int
    imagefs_offset: int


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_android_header(source: Path) -> dict[str, int | str]:
    source_bytes = source.stat().st_size
    if source_bytes < 40:
        raise ValueError("Android-style image is too short for its fixed header")
    with source.open("rb") as stream:
        header = stream.read(40)
    if header[:8] != MAGIC:
        raise ValueError("unrecognized MHI2 Android-style image signature")
    (kernel_size, kernel_addr, ramdisk_size, ramdisk_addr, second_size,
     second_addr, tags_addr, page_size) = ANDROID_HEADER.unpack_from(header, 8)
    if not 0 < kernel_size <= MAX_COMPRESSED_BYTES:
        raise ValueError(f"unsafe compressed kernel span: {kernel_size}")
    if page_size < 512 or page_size > 1024 * 1024 or page_size & (page_size - 1):
        raise ValueError(f"invalid image page size: {page_size}")
    if page_size + kernel_size > source_bytes:
        raise ValueError("compressed kernel extends beyond source image")
    return {"magic_hex": header[:8].hex(), "kernel_size": kernel_size,
            "kernel_addr": kernel_addr, "ramdisk_size": ramdisk_size,
            "ramdisk_addr": ramdisk_addr, "second_size": second_size,
            "second_addr": second_addr, "tags_addr": tags_addr,
            "page_size": page_size, "source_bytes": source_bytes}


def decompress_module(source: Path, kernel_output: Path,
                      imagefs_output: Path) -> dict[str, object]:
    """Decode a zlib kernel and carve its bounded QNX ImageFS to new files."""
    android = parse_android_header(source)
    kernel_start = int(android["page_size"])
    kernel_size = int(android["kernel_size"])
    with source.open("rb") as stream:
        stream.seek(kernel_start)
        compressed = stream.read(kernel_size)
    if len(compressed) != kernel_size:
        raise IOError("truncated compressed kernel")
    decoder = zlib.decompressobj()
    kernel = decoder.decompress(compressed, MAX_DECOMPRESSED_BYTES + 1)
    if len(kernel) > MAX_DECOMPRESSED_BYTES or decoder.unconsumed_tail:
        raise ValueError("decompressed kernel exceeds configured size limit")
    kernel += decoder.flush(MAX_DECOMPRESSED_BYTES + 1 - len(kernel))
    if len(kernel) > MAX_DECOMPRESSED_BYTES:
        raise ValueError("decompressed kernel exceeds configured size limit")
    if not decoder.eof or decoder.unused_data:
        raise ValueError("kernel span is not exactly one complete zlib stream")
    if kernel_output.exists() or imagefs_output.exists():
        raise FileExistsError("refusing to overwrite a prior decoded artifact")

    startup_offset = kernel.find(QNX_SIGNATURE, 0, min(len(kernel), 64 * 1024))
    if startup_offset < 0 or startup_offset + QNX_STARTUP.size > len(kernel):
        raise ValueError("decompressed kernel has no bounded QNX startup header")
    fields = QNX_STARTUP.unpack_from(kernel, startup_offset)
    (signature, version, flags1, flags2, header_size, machine, startup_vaddr,
     paddr_bias, image_paddr, ram_paddr, ram_size, startup_size, stored_size,
     imagefs_paddr, imagefs_size, preboot_size, _reserved, addr_off) = fields
    if signature != int.from_bytes(QNX_SIGNATURE, "little"):
        raise ValueError("invalid QNX startup signature")
    compression_type = (flags1 >> 2) & 0x7
    if compression_type != 0:
        raise ValueError(f"unsupported inner QNX compression type: {compression_type}")
    if header_size < QNX_STARTUP.size or header_size > startup_size:
        raise ValueError("invalid QNX startup header size")
    if startup_size < header_size or startup_size > len(kernel):
        raise ValueError("invalid QNX startup payload size")
    imagefs_start = startup_offset + startup_size
    imagefs_end = imagefs_start + imagefs_size
    if imagefs_size <= 0 or imagefs_end > len(kernel):
        raise ValueError("QNX ImageFS span is outside decompressed kernel")
    if kernel[imagefs_start:imagefs_start + len(IMAGEFS_SIGNATURE)] != IMAGEFS_SIGNATURE:
        raise ValueError("QNX startup header does not point at an ImageFS signature")

    kernel_output.parent.mkdir(parents=True, exist_ok=True)
    imagefs_output.parent.mkdir(parents=True, exist_ok=True)
    with kernel_output.open("xb") as stream:
        stream.write(kernel)
    with imagefs_output.open("xb") as stream:
        stream.write(kernel[imagefs_start:imagefs_end])

    startup = QnxStartup(startup_offset, version, flags1, flags2, header_size,
                         machine, startup_vaddr, paddr_bias, image_paddr,
                         ram_paddr, ram_size, startup_size, stored_size,
                         imagefs_paddr, imagefs_size, preboot_size, addr_off,
                         imagefs_start)
    return {"container": android,
            "compressed_kernel_sha256": hashlib.sha256(compressed).hexdigest(),
            "decompressed_kernel_bytes": len(kernel),
            "decompressed_kernel_sha256": hashlib.sha256(kernel).hexdigest(),
            "qnx_startup": {**asdict(startup), "compression_type": compression_type},
            "kernel_output_bytes": kernel_output.stat().st_size,
            "kernel_output_sha256": sha256_file(kernel_output),
            "imagefs_output_bytes": imagefs_output.stat().st_size,
            "imagefs_output_sha256": sha256_file(imagefs_output)}
