"""Bounds tests for the deliberately partial MH2P stage2 LZ4 probe."""

import importlib.util
from pathlib import Path
import unittest


MODULE = Path(__file__).resolve().parents[1] / "tools" / "experimental" / "extract_mh2p_stage2_imagefs.py"
SPEC = importlib.util.spec_from_file_location("extract_mh2p_stage2_imagefs", MODULE)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class Lz4PrefixTests(unittest.TestCase):
    def test_literal_only_block(self) -> None:
        consumed, output = probe.decode_lz4_block_to_limit(b"\x50hello", 5)
        self.assertEqual(consumed, 6)
        self.assertEqual(output, b"hello")

    def test_match_copy(self) -> None:
        consumed, output = probe.decode_lz4_block_to_limit(b"\x15a\x01\x00", 10)
        self.assertEqual(consumed, 4)
        self.assertEqual(output, b"a" * 10)

    def test_zero_or_out_of_range_offset_rejected(self) -> None:
        with self.assertRaises(ValueError):
            probe.decode_lz4_block_to_limit(b"\x00\x00\x00", 1)

    def test_truncated_literal_rejected(self) -> None:
        with self.assertRaises(ValueError):
            probe.decode_lz4_block_to_limit(b"\x50hell", 5)

    def test_output_limit_is_bounded(self) -> None:
        with self.assertRaises(ValueError):
            probe.decode_lz4_block_to_limit(b"\x50hello", probe.MAX_BLOCK_LIMIT + 1)


if __name__ == "__main__":
    unittest.main()
