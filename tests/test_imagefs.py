# SPDX-License-Identifier: GPL-3.0-only
"""Synthetic ImageFS structure tests; no source firmware is included."""

import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest


TOOLS = Path(__file__).resolve().parents[1] / "tools"
for name in ("filesystem_readers", "imagefs"):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules[name] = module
    spec.loader.exec_module(module)

from imagefs import inventory_imagefs  # noqa: E402


def attr(size: int, inode: int, mode: int) -> bytes:
    return struct.pack("<HHIIIII", size, 0, inode, mode, 0, 0, 0)


def make_image(path: Path, file_path: bytes = b"hello.txt\0") -> None:
    root = attr(28, 1, 0o040755) + b"\0\0\0\0"
    body = bytearray(attr(0, 2, 0o100644) + b"\0" * 8 + file_path)
    body.extend(b"\0" * (-len(body) % 4))
    struct.pack_into("<H", body, 0, len(body))
    dir_table = root + body
    data_offset = 92 + len(dir_table)
    struct.pack_into("<I", body, 24, data_offset)
    struct.pack_into("<I", body, 28, 5)
    dir_table = root + body
    image_size = data_offset + 5 + 4
    header = bytearray(92)
    header[:7] = b"imagefs"
    header[7] = 0x04
    struct.pack_into("<III", header, 8, image_size, 92 + len(dir_table), 92)
    path.write_bytes(header + dir_table + b"hello" + b"\0" * 4)


class ImageFsTests(unittest.TestCase):
    def test_inventory_file_and_root_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "test.imagefs"
            make_image(image)
            parsed = inventory_imagefs(image)
        self.assertEqual([entry["type"] for entry in parsed["entries"]], ["directory", "file"])
        self.assertEqual(parsed["entries"][1]["path"], "hello.txt")
        self.assertEqual(parsed["entries"][1]["bytes"], 5)

    def test_rejects_parent_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            image = Path(temporary) / "bad.imagefs"
            make_image(image, b"../escape\0")
            with self.assertRaisesRegex(ValueError, "unsafe ImageFS path"):
                inventory_imagefs(image)


if __name__ == "__main__":
    unittest.main()
