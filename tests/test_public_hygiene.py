"""Repository-publication hygiene checks."""

from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_TEXT = (
    "CaneTLOTW/M.I.B._Research",
    "M.I.B._Research",
    "MIBResearch",
    "E:\\MIB\\",
    "E:/MIB/",
    "OneDrive-MIB-Tools",
)

FORBIDDEN_TRACKED_SUFFIXES = {
    ".7z", ".zip", ".img", ".bin", ".ifs", ".efs", ".jxe", ".jar",
    ".class", ".so", ".dll", ".exe",
}


class PublicHygieneTests(unittest.TestCase):
    def test_no_private_research_markers_in_text_files(self) -> None:
        paths = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT
        ).decode("utf-8").split("\0")
        offenders: list[str] = []
        for rel in filter(None, paths):
            path = ROOT / rel
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for marker in FORBIDDEN_TEXT:
                if marker in text:
                    offenders.append(f"{rel}: {marker}")
        self.assertEqual(offenders, [], "\n".join(offenders))

    def test_no_firmware_or_generated_binary_artifacts_are_tracked(self) -> None:
        paths = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT
        ).decode("utf-8").split("\0")
        offenders = [
            rel for rel in filter(None, paths)
            if Path(rel).suffix.casefold() in FORBIDDEN_TRACKED_SUFFIXES
        ]
        self.assertEqual(offenders, [], "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
