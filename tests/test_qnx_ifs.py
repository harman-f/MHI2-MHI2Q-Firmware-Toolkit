# SPDX-License-Identifier: GPL-3.0-only
"""QNX UCL IFS framing tests; no vehicle firmware is embedded."""

import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch


TOOLS = Path(__file__).resolve().parents[1] / "tools"
for name in ("ucl_nrv2b", "qnx_ifs"):
    spec = importlib.util.spec_from_file_location(name, TOOLS / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

import qnx_ifs  # noqa: E402
from ucl_nrv2b import decompress_nrv2b  # noqa: E402


def make_ifs(path: Path, imagefs: bytes, prefix: bytes = bytes(8)) -> bytes:
    startup_size = 0x100
    stored_size = startup_size + 2 + 1 + 2 + 4
    startup = qnx_ifs.STARTUP.pack(
        int.from_bytes(qnx_ifs.STARTUP_MAGIC, "little"), 1, 0x0D, 0,
        startup_size, 40, 0, 0, 0, 0, len(imagefs), startup_size,
        stored_size, 0, len(imagefs), 8, bytes(6), 0)
    header = prefix + bytes(8) + startup + bytes(startup_size - len(startup))
    payload = b"\x00\x01\x01\x00\x00TAIL"
    image = header + payload
    path.write_bytes(image)
    return image


class QnxUclIfsTests(unittest.TestCase):
    def test_parses_bounded_frame_list_and_preserves_trailer(self) -> None:
        expected = b"imagefs" + bytes(85)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "ifs.ifs"
            make_ifs(source, expected)
            output = root / "decoded.imagefs"
            with patch.object(qnx_ifs, "decompress_nrv2b", return_value=expected):
                result = qnx_ifs.decompress_ucl_ifs(source, output)
            self.assertEqual(output.read_bytes(), expected)
            self.assertEqual(result["blocks"], 1)
            self.assertEqual(result["trailing_bytes_hex"], "5441494c")

    def test_finds_startup_header_after_variable_prefix_and_ignores_false_marker(self) -> None:
        expected = b"imagefs" + bytes(85)
        prefix = bytearray(0x18000)
        prefix[0x120:0x124] = qnx_ifs.STARTUP_MAGIC
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "prefixed.ifs"
            make_ifs(source, expected, bytes(prefix))
            with patch.object(qnx_ifs, "decompress_nrv2b", return_value=expected):
                result = qnx_ifs.decompress_ucl_ifs(source, root / "decoded.imagefs")
            self.assertEqual(result["startup_header"]["offset"], 0x18008)

    def test_refuses_multiple_structurally_valid_start_headers(self) -> None:
        expected = b"imagefs" + bytes(85)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first.ifs"
            second = root / "second.ifs"
            make_ifs(first, expected)
            make_ifs(second, expected)
            source = root / "ambiguous.ifs"
            source.write_bytes(first.read_bytes() + second.read_bytes())
            with self.assertRaisesRegex(ValueError, "multiple structurally valid"):
                qnx_ifs.decompress_ucl_ifs(source, root / "decoded.imagefs")

    def test_rejects_truncated_nrv2b_input(self) -> None:
        with self.assertRaises((ValueError, IndexError)):
            decompress_nrv2b(b"\x00", max_output_bytes=16)

    def test_rejects_qnx_startup_with_wrong_compression(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "wrong.ifs"
            imagefs = b"imagefs" + bytes(85)
            startup_size = 0x100
            startup = list(qnx_ifs.STARTUP.unpack(bytes(qnx_ifs.STARTUP.size)))
            startup[0] = int.from_bytes(qnx_ifs.STARTUP_MAGIC, "little")
            startup[1] = 1
            startup[2] = 1
            startup[4] = startup_size
            startup[11] = startup_size
            startup[12] = startup_size
            startup[14] = len(imagefs)
            source.write_bytes(bytes(8) + qnx_ifs.STARTUP.pack(*startup) + bytes(startup_size - qnx_ifs.STARTUP.size))
            with self.assertRaisesRegex(ValueError, "not UCL-compressed"):
                qnx_ifs.decompress_ucl_ifs(source, Path(temporary) / "out.img")


if __name__ == "__main__":
    unittest.main()
