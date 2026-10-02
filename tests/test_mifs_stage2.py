# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic safety tests for the LZOZ wrapper reader."""

from io import BytesIO
from pathlib import Path
import importlib.util
import struct
import sys
import tempfile
import unittest


MODULE = Path(__file__).resolve().parents[1] / "tools" / "mifs_stage2.py"
SPEC = importlib.util.spec_from_file_location("mifs_stage2", MODULE)
assert SPEC is not None and SPEC.loader is not None
mifs_stage2 = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = mifs_stage2
SPEC.loader.exec_module(mifs_stage2)


def fixture_image() -> bytes:
    image = bytearray(0x1000)
    image[:4] = b"LZOZ"
    struct.pack_into("<I", image, 4, 0x200000)
    struct.pack_into("<I", image, 8, 0x100)
    # One 0x100-byte compressed block at 0x800; rest is alignment/padding.
    return bytes(image)


class LzozHeaderTests(unittest.TestCase):
    def test_parses_header_and_block_bounds(self) -> None:
        data = fixture_image()
        result = mifs_stage2.parse_container(BytesIO(data), len(data))
        self.assertEqual(result.declared_block_bytes, 0x200000)
        self.assertEqual([(b.offset, b.compressed_bytes) for b in result.blocks], [(0x800, 0x100)])
        self.assertEqual(result.payload_end, 0xA00)

    def test_two_blocks_after_sector_aligned_block(self) -> None:
        data = bytearray(0xE00)
        data[:4] = b"LZOZ"
        struct.pack_into("<I", data, 4, 0x200000)
        struct.pack_into("<I", data, 8, 0x200)
        struct.pack_into("<I", data, 12, 0x100)
        result = mifs_stage2.parse_container(BytesIO(data), len(data))
        self.assertEqual([(b.offset, b.compressed_bytes) for b in result.blocks],
                         [(0x800, 0x200), (0xA00, 0x100)])
        self.assertEqual(result.payload_end, 0xC00)

    def test_rejects_wrong_magic(self) -> None:
        data = bytearray(fixture_image())
        data[:4] = b"NOPE"
        with self.assertRaises(ValueError):
            mifs_stage2.parse_container(BytesIO(data), len(data))

    def test_rejects_block_outside_image(self) -> None:
        data = bytearray(fixture_image())
        struct.pack_into("<I", data, 8, 0x2000)
        with self.assertRaises(ValueError):
            mifs_stage2.parse_container(BytesIO(data), len(data))

    def test_rejects_unterminated_block_table(self) -> None:
        data = bytearray(fixture_image())
        for offset in range(8, 0x200, 4):
            struct.pack_into("<I", data, offset, 1)
        with self.assertRaises(ValueError):
            mifs_stage2.parse_container(BytesIO(data), len(data))

    def test_rejects_oversized_declared_output_block(self) -> None:
        data = bytearray(fixture_image())
        struct.pack_into("<I", data, 4, 0xFFFFFFFF)
        with self.assertRaises(ValueError):
            mifs_stage2.parse_container(BytesIO(data), len(data))

    def test_decompressor_writes_additively_and_checks_expanded_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.img"
            target = Path(directory) / "decoded.imagefs"
            source.write_bytes(fixture_image())
            result = mifs_stage2.decompress_container(source, target,
                                                     decompress=lambda _data, _limit: b"decoded")
            self.assertEqual(target.read_bytes(), b"decoded")
            self.assertEqual(result["blocks"], 1)
            with self.assertRaises(FileExistsError):
                mifs_stage2.decompress_container(source, target,
                                                 decompress=lambda _data, _limit: b"decoded")

    def test_rejects_expanded_block_larger_than_header(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.img"
            target = Path(directory) / "decoded.imagefs"
            source.write_bytes(fixture_image())
            with self.assertRaises(ValueError):
                mifs_stage2.decompress_container(source, target,
                                                 decompress=lambda _data, limit: b"x" * (limit + 1))


if __name__ == "__main__":
    unittest.main()
