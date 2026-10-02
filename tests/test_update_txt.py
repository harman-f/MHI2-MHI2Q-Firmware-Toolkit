# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
from pathlib import Path
import unittest

MODULE = Path(__file__).resolve().parents[1] / "tools" / "update_txt.py"
SPEC = importlib.util.spec_from_file_location("update_txt", MODULE)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class UpdateTxtTests(unittest.TestCase):
    def test_refreshes_meta_and_crc(self):
        meta='[common]\nMetafileChecksum = "' + 'a'*40 + '"\n'
        update='CRC = 00000000\nMetafileCRC = old\ninitiator = HMI\n'
        refreshed, report = mod.refresh(update, meta)
        self.assertIn('MetafileCRC = ' + 'a'*40, refreshed)
        self.assertEqual(report["CRC"], mod.crc_without_crc_line(refreshed))

    def test_skip_mode(self):
        meta='[common]\nskipMetaCRC = "true"\n'
        self.assertEqual(mod.metainfo_crc_value(meta), "skip")


if __name__ == "__main__":
    unittest.main()
