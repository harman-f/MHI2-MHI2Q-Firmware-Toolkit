# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic MHI2 Android-style/QNX image wrapper tests."""

import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
import zlib


MODULE = Path(__file__).resolve().parents[1] / "tools" / "android_image.py"
SPEC = importlib.util.spec_from_file_location("android_image", MODULE)
assert SPEC is not None and SPEC.loader is not None
android_image = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = android_image
SPEC.loader.exec_module(android_image)


def make_container(path: Path, *, signature: bytes = android_image.MAGIC) -> bytes:
    imagefs = b"imagefs" + bytes(85)
    startup = android_image.QNX_STARTUP.pack(
        int.from_bytes(android_image.QNX_SIGNATURE, "little"), 1, 0, 0,
        0x100, 40, 0, 0, 0, 0, 0, 0x100, 0x100 + len(imagefs),
        0, len(imagefs), 0, bytes(6), 0)
    kernel = bytes(8) + startup + bytes(0x100 - len(startup)) + imagefs
    compressed = zlib.compress(kernel)
    page_size = 0x800
    blob = bytearray(page_size)
    blob[:8] = signature
    android_image.ANDROID_HEADER.pack_into(
        blob, 8, len(compressed), 0, 0, 0, 0, 0, 0, page_size)
    blob.extend(compressed)
    path.write_bytes(blob)
    return imagefs


class AndroidImageTests(unittest.TestCase):
    def test_decompresses_qnx_imagefs_and_reports_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "stage1.img"
            expected = make_container(source)
            kernel = root / "out" / "kernel.bin"
            imagefs = root / "out" / "imagefs.img"
            result = android_image.decompress_module(source, kernel, imagefs)
            self.assertEqual(imagefs.read_bytes(), expected)
            self.assertEqual(kernel.stat().st_size, result["decompressed_kernel_bytes"])
            self.assertEqual(result["qnx_startup"]["imagefs_size"], len(expected))

    def test_rejects_wrong_container_magic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "bad.img"
            make_container(source, signature=b"notmagic")
            with self.assertRaisesRegex(ValueError, "signature"):
                android_image.parse_android_header(source)

    def test_rejects_payload_outside_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "bad.img"
            make_container(source)
            blob = bytearray(source.read_bytes())
            struct.pack_into("<I", blob, 8, len(blob))
            source.write_bytes(blob)
            with self.assertRaisesRegex(ValueError, "extends beyond"):
                android_image.parse_android_header(source)


if __name__ == "__main__":
    unittest.main()
