# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "tools" / "binary_probe.py"
SPEC = importlib.util.spec_from_file_location("binary_probe", MODULE)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class BinaryProbeTests(unittest.TestCase):
    def test_printable_run_is_bounded_and_marked_truncated(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "long.bin"
            path.write_bytes(b"A" * 10000 + b"\x00")
            report = mod.analyze_binary(path, max_strings=4, min_string=5, max_string_length=64)
            self.assertEqual(len(report["strings"]), 1)
            self.assertEqual(len(report["strings"][0]["text"]), 64)
            self.assertTrue(report["strings"][0]["truncated"])
            self.assertEqual(report["string_capture"]["max_length"], 64)

    def test_rejects_string_cap_smaller_than_minimum(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.bin"
            path.write_bytes(b"abcdef")
            with self.assertRaises(ValueError):
                mod.analyze_binary(path, min_string=8, max_string_length=4)

    def test_quickboot_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"qb.bin"
            path.write_bytes(b"X"*32+b"KERNEL_PRIMARY\x00KERNEL_RECOVERY\x00ANDROID!\x00hello-world")
            report=mod.analyze_binary(path)
            self.assertIn("quickboot boot-selection-loader candidate", report["classifications"])
            self.assertIn("kernel_primary", report["markers"])
            self.assertEqual(report["source"], "qb.bin")


if __name__ == "__main__":
    unittest.main()
