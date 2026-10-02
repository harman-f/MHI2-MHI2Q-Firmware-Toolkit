"""Bounds tests for the validated MH2P LZ4 segment-prefix extractor."""

from pathlib import Path
import importlib.util
import unittest


MODULE = Path(__file__).resolve().parents[1] / "tools" / "experimental" / "extract_mh2p_stage2_segment_prefix.py"
SPEC = importlib.util.spec_from_file_location("extract_mh2p_stage2_segment_prefix", MODULE)
probe = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(probe)


class HeaderTests(unittest.TestCase):
    def test_reads_size_table_until_zero(self):
        header = bytearray(probe.HEADER_SIZE)
        header[:4] = b"LZ4_"
        header[4:8] = (2 * 1024 * 1024).to_bytes(4, "little")
        header[8:12] = (1234).to_bytes(4, "little")
        header[12:16] = (5678).to_bytes(4, "little")
        limit, sizes = probe.parse_header(bytes(header))
        self.assertEqual(limit, 2 * 1024 * 1024)
        self.assertEqual(sizes, [1234, 5678])

    def test_rejects_unknown_magic(self):
        with self.assertRaisesRegex(ValueError, "LZ4_"):
            probe.parse_header(bytes(probe.HEADER_SIZE))

    def test_rejects_unsafe_block_limit(self):
        header = bytearray(probe.HEADER_SIZE)
        header[:4] = b"LZ4_"
        header[4:8] = (probe.MAX_BLOCK_LIMIT + 1).to_bytes(4, "little")
        with self.assertRaisesRegex(ValueError, "unsafe"):
            probe.parse_header(bytes(header))


class AlignmentTests(unittest.TestCase):
    def test_aligns_sector_boundaries(self):
        self.assertEqual(probe.align_up(0x8A526), 0x8A600)
        self.assertEqual(probe.align_up(0x1C3D99), 0x1C3E00)

    def test_rejects_non_power_of_two_alignment(self):
        with self.assertRaisesRegex(ValueError, "power of two"):
            probe.align_up(10, 300)


class Lz4AuditTests(unittest.TestCase):
    def test_literal_only_block(self):
        self.assertEqual(probe.audit_lz4_block(b"\x50hello", 5), (5, 1))

    def test_match_and_final_literals(self):
        # Four literals, then a four-byte back-reference, then one literal.
        self.assertEqual(probe.audit_lz4_block(b"\x40abcd\x04\x00\x10!", 9), (9, 2))

    def test_rejects_truncated_literals(self):
        with self.assertRaisesRegex(ValueError, "truncated LZ4 literals"):
            probe.audit_lz4_block(b"\x50hell", 10)

    def test_rejects_invalid_offset(self):
        with self.assertRaisesRegex(ValueError, "invalid LZ4 match offset"):
            probe.audit_lz4_block(b"\x10a\x02\x00\x00", 10)

    def test_rejects_missing_final_sequence(self):
        with self.assertRaisesRegex(ValueError, "final literal"):
            probe.audit_lz4_block(b"\x10a\x01\x00", 10)

    def test_rejects_output_over_limit(self):
        with self.assertRaisesRegex(ValueError, "output exceeds"):
            probe.audit_lz4_block(b"\x50hello", 4)


if __name__ == "__main__":
    unittest.main()
