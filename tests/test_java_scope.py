# SPDX-License-Identifier: GPL-3.0-only
"""Tests for the optional Java/CarPlay export configuration."""

from pathlib import Path
import re
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CarPlayFilterTests(unittest.TestCase):
    def test_filter_matches_initial_carplay_shortlist(self) -> None:
        path = PROJECT_ROOT / "config" / "carplay-cfr-jarfilter.regex"
        lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip() and not line.lstrip().startswith("#")]
        self.assertEqual(len(lines), 1)
        pattern = re.compile(lines[0])
        targets = (
            "de/esolutions/hmi/widgets/audi/evo/high/widgets/CombiMapController.class",
            "de/vw/mib/asl/internal/mostkombi/streamsink/usecases/ChangeDataRate.class",
            "de/vw/mib/asl/internal/mostkombi/streamsink/usecases/ChangeDataRateSequence.class",
        )
        for target in targets:
            with self.subTest(target=target):
                self.assertRegex(target, pattern)


if __name__ == "__main__":
    unittest.main()
