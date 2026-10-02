# External analysis and post-processing tools

The core extractor deliberately keeps firmware parsing separate from optional reverse-engineering, Java and cross-compilation toolchains. Firmware data and third-party executables are not bundled here.

## Java payloads: lsd.jxe to JAR and Java

Use `--component java` to export the recovered `lsd.jxe`. Conversion/decompilation is a separate external step.

### Preferred external conversion/research route: luka-dev/jxe2jar

- Project: https://github.com/luka-dev/jxe2jar
- Reviewed pin: `9eeb45bbf14bf8afe3452c7be96a4d1f0206a286` (reviewed 2026-10-02)
- No clear top-level license grant was found during the 2026-09-28 review.

For **new JXE-to-JAR conversions and current Java-analysis baselines, prefer `luka-dev/jxe2jar` at the pinned revision above**. This is the route used as the comparison baseline for this toolkit's current firmware research.

Because no clear top-level license grant was found at the reviewed pin, this repository does not copy, vendor or redistribute upstream source. `tools/jxe2jar/convert-jxe.ps1` is a project-authored wrapper that fetches/checks out the exact external commit, verifies a clean worktree, runs the converter, and records the commit plus input/output hashes.

### Licensed known-working alternative: lsdtool

- Project: https://github.com/JeniCzech92/lsdtool
- Reviewed tree: `4bf44aac95f03cf3b81985dd9ccd9c81fb1ef63d`
- Project license: MIT.
- The reviewed tree carries separate MIT notices for its bundled JXE2JAR utility and CFR.
- It provides a practical `lsd.jxe -> lsd.jar -> decompiled Java` workflow.

`lsdtool` remains useful as a clearly licensed known-working alternative and cross-check, but it is not the preferred baseline for new comparisons.

For manual/video-oriented discovery, YouTube search can help locate walkthroughs:
https://www.youtube.com/results?search_query=MIB2+lsd.jxe+JXE2JAR

This is intentionally a discovery link rather than a vendored tutorial or downloader. Verify the exact tool/revision shown by any third-party video before reproducing it.

### CFR

- Version used in an earlier validated workflow: 0.152
- SHA-256: `f686e8f3ded377d7bc87d216a90e9e9512df4156e75b06c655a16648ae8765b2`
- License: MIT.
- Project: https://github.com/leibnitz27/cfr

## Native analysis: Ghidra

- Project: https://github.com/NationalSecurityAgency/ghidra
- Recommended for ELF/shared-library inspection, ARM/QNX disassembly and headless decompilation.
- No Ghidra binaries are bundled.
- Current reviewed public release on 2026-10-02: Ghidra 12.1.4.
- Release archive SHA-256 published upstream: `ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db`.
- License: Apache-2.0 for the Ghidra project; separately review bundled third-party notices.

For reproducible research, record the exact Ghidra release, processor/language selection, loader settings, image base and analysis options in the resulting report.

## QNX 6.5 / ARMv7 build and inspection

A useful external cross-toolchain reference is:

- https://github.com/luka-dev/qnx65-armv7-toolchain
- Reviewed repository HEAD during this audit: `baa45224f18ae6b13c2e9c77c6663bb8181eb6a1`

This repository does not vendor that toolchain, a QNX SDP, QNX headers/libraries, or container images derived from them. QNX components can carry separate proprietary licensing requirements. Use only material you are authorized to possess and redistribute.

## Filesystem builders

Extraction support does not imply rebuild support. QNX IFS/EFS/QNX6 image creation may require platform-specific builders or independently implemented writers. See `REPACK_AND_METAINFO.md` for the current capability matrix.

## Reproducibility rule

When an external tool materially changes an artifact, record at least:

- tool/project name;
- version or commit;
- executable/archive SHA-256 when practical;
- command line or equivalent settings;
- input SHA-256;
- output SHA-256;
- whether the tool was used only for analysis or changed bytes.

Do not copy external binaries into this repository merely to make a workflow convenient.
