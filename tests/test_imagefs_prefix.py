"""Synthetic bounds test for directory-validated incomplete ImageFS recovery."""

from pathlib import Path
import struct
import sys
import tempfile
import unittest


TOOLS_ROOT = Path(__file__).resolve().parents[1] / "tools"
sys.path.insert(0, str(TOOLS_ROOT))
from imagefs import inventory_imagefs, materialize_imagefs_prefix  # noqa: E402


def entry(path: bytes, offset: int, size: int) -> bytes:
    payload = struct.pack("<II", offset, size) + path + b"\0"
    entry_size = (24 + len(payload) + 3) & ~3
    return (struct.pack("<HHIIIII", entry_size, 0, 1, 0o100644, 0, 0, 0)
            + payload).ljust(entry_size, b"\0")


class ImagefsPrefixTests(unittest.TestCase):
    def test_only_materializes_complete_file_extent(self):
        directory = entry(b"a", 164, 4) + entry(b"b", 176, 4)
        self.assertEqual(len(directory), 72)
        header = bytearray(92)
        header[:8] = b"imagefs\x04"
        struct.pack_into("<III", header, 8, 200, 164, 92)
        prefix = bytes(header) + directory + b"data"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / "partial.img"
            image.write_bytes(prefix)
            with self.assertRaisesRegex(ValueError, "invalid ImageFS declared size"):
                inventory_imagefs(image)
            inventory = inventory_imagefs(image, allow_incomplete=True)
            self.assertEqual(inventory["complete_file_entries"], 1)
            self.assertEqual(inventory["incomplete_file_entries"], 1)
            result = materialize_imagefs_prefix(image, root / "files", root / "metadata.json")
            self.assertEqual(result["file_count"], 1)
            self.assertEqual((root / "files" / "a").read_bytes(), b"data")
            self.assertFalse((root / "files" / "b").exists())


if __name__ == "__main__":
    unittest.main()
