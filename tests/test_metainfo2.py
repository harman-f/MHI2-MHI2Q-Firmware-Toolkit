# SPDX-License-Identifier: GPL-3.0-only
import importlib.util
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "tools" / "metainfo2.py"
SPEC = importlib.util.spec_from_file_location("metainfo2", MODULE)
assert SPEC and SPEC.loader
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class MetainfoTests(unittest.TestCase):
    def test_refreshes_file_and_meta_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "Demo" / "version" / "MARKER"
            payload.parent.mkdir(parents=True)
            payload.write_bytes(b"abc")
            text = (
                '[common]\nMetafileChecksum = "' + '0' * 40 + '"\n\n'
                '[Demo\\version\\0\\default\\File]\n'
                'Source = "../../MARKER"\n'
                'FileSize = "0"\n'
                'CheckSum = "' + '0' * 40 + '"\n'
            )
            refreshed, report = mod.audit_and_refresh(text, root)
            self.assertIn('FileSize = "3"', refreshed)
            self.assertIn(mod.sha1_file(payload), refreshed)
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(
                mod.metafile_checksum(refreshed),
                next(row["new"] for row in report["changes"]
                     if row["key"] == "MetafileChecksum"),
            )

    def test_chunked_checksums_insert_numbered_entries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "A" / "f.bin"
            payload.parent.mkdir()
            payload.write_bytes(b"a" * 10 + b"b" * 10)
            text = (
                '[A\\Application]\n'
                'FileName = "f.bin"\n'
                'FileSize = "0"\n'
                'CheckSumSize = "10"\n'
                'CheckSum = "old"\n'
            )
            refreshed, _ = mod.audit_and_refresh(text, root)
            self.assertIn(f'CheckSum = "{mod.sha1_bytes(b"a" * 10)}"', refreshed)
            self.assertIn(f'CheckSum1 = "{mod.sha1_bytes(b"b" * 10)}"', refreshed)

    def test_stale_numbered_checksum_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "A" / "f.bin"
            payload.parent.mkdir()
            payload.write_bytes(b"abc")
            text = (
                '[A\\Application]\n'
                'FileName = "f.bin"\n'
                'FileSize = "3"\n'
                'CheckSumSize = "10"\n'
                'CheckSum = "old"\n'
                'CheckSum1 = "stale"\n'
            )
            refreshed, report = mod.audit_and_refresh(text, root)
            self.assertNotIn("CheckSum1", refreshed)
            self.assertTrue(any(change["action"] == "remove" for change in report["changes"]))

    def test_dir_plans_hashes_txt_without_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload_dir = root / "D"
            payload_dir.mkdir()
            (payload_dir / "a").write_bytes(b"abc")
            text = (
                '[D\\Dir]\n'
                'FileSize = "0"\n'
                'CheckSumSize = "2"\n'
                'CheckSum = "old"\n'
            )
            refreshed, report, sidecars = mod._plan_refresh(text, root, "full")
            self.assertIn(payload_dir / "hashes.txt", sidecars)
            self.assertFalse((payload_dir / "hashes.txt").exists())
            self.assertIn('FileName = "a"', sidecars[payload_dir / "hashes.txt"].decode())
            self.assertTrue(report["sidecar_changes"])
            self.assertIn("CheckSum1", refreshed)

    def test_signed_prefix_is_byte_preserved_in_auto_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "X" / "f"
            payload.parent.mkdir()
            payload.write_bytes(b"abc")
            prefix = (
                '[common]\r\n'
                'MetafileChecksum = "PROTECTED"\r\n'
                'signature1 = "ABC"\r\n'
            )
            tail = (
                '[X\\Application]\r\n'
                'FileName = "f"\r\n'
                'FileSize = "0"\r\n'
                'CheckSum = "old"\r\n'
            )
            refreshed, report = mod.audit_and_refresh(prefix + tail, root)
            self.assertTrue(refreshed.startswith(prefix))
            self.assertTrue(report["signed_prefix_preserved"])
            self.assertEqual(report["mode"], "signed-tail")
            self.assertIn('MetafileChecksum = "PROTECTED"', refreshed)
            self.assertNotIn("\n", refreshed.replace("\r\n", ""))

    def test_bootloader_sections_are_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "B" / "bl.bin"
            payload.parent.mkdir()
            payload.write_bytes(b"boot")
            text = (
                '[B\\Bootloader]\n'
                'FileName = "bl.bin"\n'
                'FileSize = "0"\n'
                'CheckSum = "old"\n'
            )
            refreshed, _ = mod.audit_and_refresh(text, root)
            self.assertIn(mod.sha1_file(payload), refreshed)

    def test_finalscript_plans_directory_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            script = scripts / "final.sh"
            script.write_bytes(b"echo hi\n")
            text = (
                '[common]\n'
                'FinalScript = "./scripts/final.sh"\n'
                'FinalScriptChecksum = "old"\n\n'
                '[scripts\\dir]\n'
                'FileSize = "0"\n'
                'CheckSum = "old"\n'
            )
            refreshed, _, sidecars = mod._plan_refresh(text, root, "full")
            self.assertIn(scripts / "hashes.txt", sidecars)
            self.assertIn(mod.chunk_sha1_file(script)[1][0], refreshed)

    def test_finalscript_reuses_matching_dir_chunk_size(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            scripts = root / "scripts"
            scripts.mkdir()
            script = scripts / "final.sh"
            script.write_bytes(b"abcdefghij")
            text = (
                '[common]\n'
                'FinalScript = "./scripts/final.sh"\n'
                'FinalScriptChecksum = "old"\n\n'
                '[scripts\\dir]\n'
                'FileSize = "0"\n'
                'CheckSumSize = "3"\n'
                'CheckSum = "old"\n'
            )
            refreshed, report, sidecars = mod._plan_refresh(text, root, "full")
            self.assertEqual(report["status"], "PASS")
            sidecar = sidecars[scripts / "hashes.txt"]
            hashes = sidecar.decode()
            self.assertIn('CheckSumSize = "3"', hashes)
            self.assertIn(mod.sha1_bytes(b"abc"), hashes)

            for path, data in sidecars.items():
                path.write_bytes(data)
            refreshed_again, report_again, sidecars_again = mod._plan_refresh(
                refreshed, root, "full"
            )
            self.assertEqual(refreshed_again, refreshed)
            self.assertEqual(sidecars_again, {})
            self.assertEqual(report_again["status"], "PASS")

    def test_dir_parent_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "package"
            root.mkdir()
            outside = Path(directory) / "outside"
            outside.mkdir()
            (outside / "secret.bin").write_bytes(b"secret")
            text = (
                '[..\\Dir]\n'
                'FileSize = "0"\n'
                'CheckSum = "old"\n'
            )
            refreshed, report, sidecars = mod._plan_refresh(text, root, "full")
            self.assertEqual(refreshed, text)
            self.assertEqual(report["status"], "REVIEW")
            self.assertTrue(any("escapes package root" in item["reason"]
                                for item in report["unresolved"]))
            self.assertEqual(sidecars, {})

    def test_dir_nested_symlink_escape_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "package"
            payload = root / "D"
            payload.mkdir(parents=True)
            outside = Path(directory) / "outside.bin"
            outside.write_bytes(b"secret")
            link = payload / "linked.bin"
            try:
                link.symlink_to(outside)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable on this platform")
            text = (
                '[D\\Dir]\n'
                'FileSize = "0"\n'
                'CheckSum = "old"\n'
            )
            refreshed, report, sidecars = mod._plan_refresh(text, root, "full")
            self.assertEqual(refreshed, text)
            self.assertEqual(report["status"], "REVIEW")
            self.assertTrue(any("directory member escapes section root" in item["reason"]
                                for item in report["unresolved"]))
            self.assertEqual(sidecars, {})

    def test_dir_hashes_use_relative_paths_for_nested_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload_dir = root / "D"
            nested = payload_dir / "sub"
            nested.mkdir(parents=True)
            (nested / "file.bin").write_bytes(b"nested")
            text = (
                '[D\\Dir]\n'
                'FileSize = "0"\n'
                'CheckSum = "old"\n'
            )
            _, _, sidecars = mod._plan_refresh(text, root, "full")
            hashes = sidecars[payload_dir / "hashes.txt"].decode()
            self.assertIn('FileName = "sub/file.bin"', hashes)
            self.assertNotIn('FileName = "file.bin"', hashes)

    def test_parent_dir_uses_planned_child_hashes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            child = root / "parent" / "child"
            child.mkdir(parents=True)
            (child / "payload.bin").write_bytes(b"payload")
            (child / "hashes.txt").write_text("stale\n", encoding="utf-8")
            text = (
                '[parent\\Dir]\n'
                'FileSize = "0"\n'
                'CheckSum = "old"\n\n'
                '[parent\\child\\Dir]\n'
                'FileSize = "0"\n'
                'CheckSum = "old"\n'
            )
            refreshed, _, sidecars = mod._plan_refresh(text, root, "full")
            child_sidecar = sidecars[child / "hashes.txt"]
            parent_sidecar = sidecars[root / "parent" / "hashes.txt"].decode()
            self.assertIn('FileName = "child/hashes.txt"', parent_sidecar)
            self.assertIn(mod.sha1_bytes(child_sidecar), parent_sidecar)

            for path, data in sidecars.items():
                path.write_bytes(data)
            refreshed_again, report_again, sidecars_again = mod._plan_refresh(
                refreshed, root, "full"
            )
            self.assertEqual(refreshed_again, refreshed)
            self.assertEqual(sidecars_again, {})
            self.assertEqual(report_again["status"], "PASS")

    def test_checksum_insertion_after_unterminated_anchor_adds_newline(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            payload = root / "A" / "f.bin"
            payload.parent.mkdir()
            payload.write_bytes(b"a" * 10 + b"b" * 10)
            text = (
                '[A\\Application]\n'
                'FileName = "f.bin"\n'
                'FileSize = "20"\n'
                'CheckSumSize = "10"\n'
                'CheckSum = "old"'
            )
            refreshed, report = mod.audit_and_refresh(text, root)
            first = mod.sha1_bytes(b"a" * 10)
            second = mod.sha1_bytes(b"b" * 10)
            self.assertIn(f'CheckSum = "{first}"\nCheckSum1 = "{second}"\n', refreshed)
            self.assertEqual(report["suspicious_non_ini_lines"], [])

    def test_flags_non_ini_line(self):
        text = '[common]\nrelease = "x"\necho unexpected\n'
        _, report = mod.audit_and_refresh(text, Path(".").resolve())
        self.assertEqual(report["status"], "REVIEW")
        self.assertEqual(report["suspicious_non_ini_lines"][0]["line"], 3)


if __name__ == "__main__":
    unittest.main()
