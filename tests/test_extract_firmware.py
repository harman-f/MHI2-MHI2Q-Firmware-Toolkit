# SPDX-License-Identifier: GPL-3.0-only
"""Pure selection tests; no firmware bytes, filesystem writes, or network."""

import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest


MODULE = Path(__file__).resolve().parents[1] / "tools" / "extract_firmware.py"
SPEC = importlib.util.spec_from_file_location("extract_firmware", MODULE)
assert SPEC is not None and SPEC.loader is not None
extractor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(extractor)


def member(path: str) -> dict[str, object]:
    return {"path": path, "size": 1, "crc": ""}


class SelectionTests(unittest.TestCase):
    def test_qnxmount_commit_is_pinned(self) -> None:
        self.assertEqual(extractor.QNXMOUNT_COMMIT,
                         "0379c064975d5bbe3595ac7e3d149ea789406794")

    def setUp(self) -> None:
        self.members = [
            member("MMX2/app/50/default/app.img"),
            member("MMX2/app/70/default/app.img"),
            member("MMX2/img_ver.txt"),
            member("RCC/ifs-root/21/default/ifs-root.ifs"),
            member("RCC/efs-system/21/default/efs-system.efs"),
            member("MMX2/efs-pers/50/default/efs-persist.img"),
            member("MMX2/efs-sys/50/default/efs-system.img"),
            member("MMX2/efs-pers/70/default/efs-persist.img"),
            member("MMX2/eifs/50/default/eifs.img"),
            member("MMX2/mifs-stage1/50/default/mifs-stage1.img"),
            member("MMX2/mifs-stage1/70/default/mifs-stage1.img"),
        ]

    def test_au57x_auto_selects_only_50_and_rcc(self) -> None:
        selected, apps, roots, efs, emergency, stage2, mmx_efs, android = extractor.select_members(
            self.members, "", "auto", Path("MHI2_ER_AU57x_K3663.7z")
        )
        self.assertEqual(len(selected), 8)
        self.assertEqual(apps, ["MMX2/app/50/default/app.img"])
        self.assertEqual(roots, ["RCC/ifs-root/21/default/ifs-root.ifs"])
        self.assertEqual(efs, ["RCC/efs-system/21/default/efs-system.efs"])
        self.assertEqual(emergency, [])
        self.assertEqual(stage2, [])
        self.assertEqual(mmx_efs, ["MMX2/efs-pers/50/default/efs-persist.img",
                                  "MMX2/efs-sys/50/default/efs-system.img"])
        self.assertEqual(android, ["MMX2/eifs/50/default/eifs.img",
                                   "MMX2/mifs-stage1/50/default/mifs-stage1.img"])

    def test_other_firmware_auto_selects_both_variants(self) -> None:
        selected, apps, _, _, _, _, mmx_efs, android = extractor.select_members(
            self.members, "", "auto", Path("MHI2_ER_SKG13_P4526_MU1440.7z")
        )
        self.assertEqual(len(selected), 11)
        self.assertEqual(len(apps), 2)
        self.assertEqual(len(mmx_efs), 3)
        self.assertEqual(len(android), 3)

    def test_renamed_archive_can_request_50_explicitly(self) -> None:
        _, apps, _, _, _, _, _, _ = extractor.select_members(
            self.members, "", "50", Path("firmware.zip")
        )
        self.assertEqual(apps, ["MMX2/app/50/default/app.img"])

    def test_case_collision_is_rejected(self) -> None:
        members = self.members + [member("RCC/IFS-ROOT/21/default/ifs-root.ifs")]
        with self.assertRaises(ValueError):
            extractor.select_members(members, "", "auto", Path("MHI2_ER_AU57x_K3663.7z"))

    def test_selects_stage2_and_emergency_images(self) -> None:
        members = self.members + [
            member("MMX2/mifs-stage2/50/default/mifs-stage2.img"),
            member("MMX2/mifs-stage2/70/default/mifs-stage2.img"),
            member("RCC/ifs-emg/21/default/ifs-emergency.ifs"),
        ]
        selected, _, _, _, emergency, stage2, _, android = extractor.select_members(
            members, "", "both", Path("MHI2_ER_SKG13_P4526_MU1440.7z")
        )
        self.assertEqual(len(selected), 14)
        self.assertEqual(emergency, ["RCC/ifs-emg/21/default/ifs-emergency.ifs"])
        self.assertEqual(stage2, ["MMX2/mifs-stage2/50/default/mifs-stage2.img",
                                  "MMX2/mifs-stage2/70/default/mifs-stage2.img"])
        self.assertEqual(len(android), 3)

    def test_rcc_component_selects_no_mmx_images(self) -> None:
        selected, apps, roots, efs, emergency, stage2, mmx_efs, android = extractor.select_members(
            self.members, "", "both", Path("MHI2_ER_SKG13_P4526_MU1440.7z"), {"rcc"})
        paths = [item["path"] for item in selected]
        self.assertEqual(apps, [])
        self.assertEqual(roots, ["RCC/ifs-root/21/default/ifs-root.ifs"])
        self.assertEqual(efs, ["RCC/efs-system/21/default/efs-system.efs"])
        self.assertEqual((emergency, stage2, mmx_efs, android), ([], [], [], []))
        self.assertTrue(all(path.startswith("RCC/") or path == "metainfo2.txt" for path in paths))

    def test_java_component_selects_stage2_only(self) -> None:
        members = self.members + [member("MMX2/mifs-stage2/50/default/mifs-stage2.img"),
                                  member("MMX2/mifs-stage2/70/default/mifs-stage2.img")]
        selected, apps, _, _, _, stage2, mmx_efs, android = extractor.select_members(
            members, "", "both", Path("MHI2_ER_SKG13_P4526_MU1440.7z"), {"java"})
        paths = [item["path"] for item in selected]
        self.assertEqual(apps, [])
        self.assertEqual(stage2, ["MMX2/mifs-stage2/50/default/mifs-stage2.img",
                                  "MMX2/mifs-stage2/70/default/mifs-stage2.img"])
        self.assertEqual((mmx_efs, android), ([], []))
        self.assertTrue(all(path.startswith("MMX2/mifs-stage2/") or path in ("MMX2/img_ver.txt", "metainfo2.txt")
                            for path in paths))

    def test_component_all_cannot_be_combined(self) -> None:
        with self.assertRaises(ValueError):
            extractor.normalize_components(["all", "rcc"])

    def test_component_filter_is_not_reported_as_variant_exclusion(self) -> None:
        members = [member("MMX2/app/70/default/app.img"),
                   member("MMX2/mifs-stage2/70/default/mifs-stage2.img")]
        self.assertEqual(extractor.count_excluded_70_members(members, "", {"rcc"}, []), 0)
        self.assertEqual(extractor.count_excluded_70_members(members, "", {"mmx"}, ["50"]), 2)
        self.assertEqual(extractor.count_excluded_70_members(members, "", {"java"}, ["50", "70"]), 0)


class ImageSelectionTests(unittest.TestCase):
    def test_detects_mmx_qnx_efs_marker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "efs-persist.img"
            image.write_bytes(b"\x10\x00\x4c\xff" + bytes(40) + b"QSSL_F3S" + bytes(32))
            self.assertTrue(extractor.looks_like_qnx_efs(image))

    def test_does_not_misclassify_arbitrary_image(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "app.img"
            image.write_bytes(b"\x00" * 4096)
            self.assertFalse(extractor.looks_like_qnx_efs(image))

    def test_reports_unparsed_selected_image_payloads(self) -> None:
        selected = ["MMX2/app/50/default/app.img",
                    "MMX2/qb-primary/50/default/qb_primary.img",
                    "RCC/tools/0/default/update.sh"]
        parsed = {"MMX2/app/50/default/app.img"}
        self.assertEqual(extractor.unparsed_image_members(selected, parsed),
                         ["MMX2/qb-primary/50/default/qb_primary.img"])

    def test_recognizes_known_quickboot_payload_only_with_all_markers(self) -> None:
        path = "MMX2/qb-primary/50/default/qb_primary.img"
        data = b"KERNEL_PRIMARY\x00KERNEL_RECOVERY\x00ANDROID!"
        result = extractor.identify_known_raw_payload(path, data)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertFalse(result["filesystem_tree"])
        self.assertIsNone(extractor.identify_known_raw_payload(path, b"KERNEL_PRIMARY"))

    def test_opaque_report_names_include_member_path_identity(self) -> None:
        digest = "a" * 64
        first = extractor.opaque_report_filename(
            "MMX2/qb-primary/50/default/qb_primary.img", digest)
        second = extractor.opaque_report_filename(
            "MMX2/qb-primary/70/default/qb_primary.img", digest)
        self.assertNotEqual(first, second)
        self.assertTrue(first.startswith("opaque-qb_primary-"))
        self.assertTrue(first.endswith("-" + digest[:12] + ".json"))

    def test_run_unknown_binary_uses_real_orchestrator_and_probe(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "qb-primary.bin"
            source.write_bytes(b"X" * 32 + b"KERNEL_PRIMARY\x00KERNEL_RECOVERY\x00ANDROID!\x00")
            output = root / "export"
            args = SimpleNamespace(
                component=["mmx"], source=source, output=output, plan=False,
                variant="auto", package_prefix=None, expected_sha256=None,
                seven_zip=None, qnxmount_root=None, dependency_root=None,
                dumpifs_dir=None, skip_emergency=False,
            )
            result = extractor.run(args)
            self.assertEqual(result["status"], "PARTIAL")
            self.assertEqual(result["output"], "export")
            self.assertEqual(result["unparsed_components"], ["qb-primary.bin"])
            self.assertEqual(len(result["opaque_binary_analysis"]), 1)
            analysis_path = output / result["opaque_binary_analysis"][0]["analysis"]
            self.assertTrue(analysis_path.is_file())


if __name__ == "__main__":
    unittest.main()
