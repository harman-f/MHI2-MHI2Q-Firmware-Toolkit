# Dependencies, provenance, and redistribution notes

This inventory describes the current source tree and observed workflow. Pins do not by themselves mean an upstream dependency is bundled or the complete toolchain is reproducible. Re-check upstream licensing before changing pins or redistributing a built environment.

## Runtime components

| Component | Used for | Provenance / pin | License and status |
|---|---|---|---|
| Python | Orchestration, parsers, tests, metadata helpers | Python 3.10+ recommended | Host runtime; record exact version for reproducible runs. |
| 7-Zip | Listing/extracting firmware archive members | Official distribution; supplied separately | Not bundled. Review the exact build license before redistributing it. |
| qnxmount | QNX6 MMX app and EFS export | NetherlandsForensicInstitute/qnxmount, commit `0379c064975d5bbe3595ac7e3d149ea789406794` | Apache-2.0; external, not vendored. |
| kaitaistruct | qnxmount parser runtime | 0.10 observed | MIT; external Python dependency. |
| crcmod | qnxmount EFS/QNX checks | 1.7 observed | MIT; external Python dependency. |
| lclevy/dumpifs | RCC compressed root IFS | commit `bb77c71bae3ebb54b8b7469ac810c890530f3213` | BSD-2-Clause in reviewed checkout; external. |
| python-lzo | RCC LZO parsing and Stage-2 LZO1Z decoding | 1.15 observed in the validated environment | GPL-2.0-only in reviewed package metadata. Not bundled. The extractor imports it in-process for selected modes. Resolve compatibility before distributing a combined GPL-3.0-only environment. |

This repository does not vendor qnxmount, dumpifs, python-lzo, python-lz4, 7-Zip or jxe2jar. The rebuilt metainfo helper also does not vendor or require the historical ConfigObj/six dependency pair. `requirements.txt` contains only kaitaistruct and crcmod; installing it alone does not enable every parser.

## Experimental parser dependency

The bounded MH2P `LZ4_` probes under `tools/experimental/` require the
external `lz4` Python package only when an actual segment is decompressed.
The unit tests for their bounds/header logic do not require it. Generated MH2P
trees remain local-only and may contain device-specific key material.

## External analysis / post-processing tools

| Tool | Purpose | Reviewed reference | Status |
|---|---|---|---|
| luka-dev/jxe2jar | **Preferred external JXE conversion/comparison baseline** | reviewed pin `9eeb45bbf14bf8afe3452c7be96a4d1f0206a286` | Obtain from upstream. No clear top-level license grant found at the reviewed pin, so it is not bundled or redistributed here. |
| JeniCzech92/lsdtool | Practical `lsd.jxe -> JAR -> Java` workflow | tree `4bf44aac95f03cf3b81985dd9ccd9c81fb1ef63d` | MIT project; external. Reviewed tree includes separate MIT notices for JXE2JAR and CFR. |
| CFR | JAR-to-Java decompilation | 0.152, SHA-256 `f686e8f3ded377d7bc87d216a90e9e9512df4156e75b06c655a16648ae8765b2` | MIT; external, not bundled. |
| Java | Runs Java decompilers/tools | Java 8 used in an earlier validated workflow | External runtime; record vendor/version. |
| NationalSecurityAgency/ghidra | ARM/QNX ELF/native analysis | Ghidra 12.1.4; release SHA-256 `ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db` | Apache-2.0 project plus third-party notices; external. |
| luka-dev/qnx65-armv7-toolchain | QNX 6.5 / ARMv7 cross-build and inspection reference | reviewed HEAD `baa45224f18ae6b13c2e9c77c6663bb8181eb6a1` | External only. QNX-derived components may carry separate proprietary licensing requirements. |

See `docs/EXTERNAL_TOOLS.md` for usage boundaries and reproducibility guidance.

## Reference-only projects and algorithms

| Reference | Purpose | Review status |
|---|---|---|
| jtang613/qnx_dumpers, commit `68424a67efbcc0ff0f63e45223a530a0f3bde3fe` | Differential/reference parser | README states MIT; not required at runtime. |
| ReverseEngDotDev/dump_hbcifs, commit `6aa607a0dc5faf7eed055531a65ec682715dfb6e` | QNX IFS/ImageFS format behavior | No license grant found at reviewed pin; reference only, no code copied. |
| UCL 1.02 | NRV2B format/algorithm reference | GPL; no UCL code linked or bundled. |
| Binary Refinery 0.11.2 | Differential test oracle for NRV2B | BSD-3-Clause; not a runtime dependency. Attribution is in `dependencies/THIRD_PARTY_NOTICES.md`. |
| luka-dev/jxe2jar, pin `9eeb45bbf14bf8afe3452c7be96a4d1f0206a286` | JXE-to-JAR format/behavior reference and preferred comparison baseline | No top-level license grant found during 2026-09-28 review; not bundled or copied into this toolkit. |
| alelec/mib2-update-hashes | Historical metainfo2/update-hash tooling lineage | External reference only; no code copied into this repository. |
| ConfigObj 5 | Dependency used by a reviewed historical hash helper | BSD-3-Clause in the supplied/reference copy; **not** a runtime dependency of this toolkit. |
| six 1.15.0 | Python 2/3 compatibility dependency used by that historical ConfigObj copy | MIT; **not** a runtime dependency of this toolkit. |
| LateAlways/mibwiki-mirror | Public historical documentation for MHI2 update metadata/recovery behavior | Documentation reference only. |

GPL is not a noncommercial-use restriction. The distinction here is the exact license compatibility and redistribution conditions. Publicly accessible source without a license grant is not automatically reusable by attribution alone.

## Packaging status

This is a source toolkit, not an all-in-one offline installer. A portable release still needs pinned dependency source/artifact hashes, a clean-environment test, corresponding notices/source offers where required, and resolution of the python-lzo GPL-2.0-only boundary before distributing a combined environment. Firmware archives and extracted trees remain outside this repository.

This is a technical provenance inventory, not legal advice; license claims are limited to the reviewed pins and package metadata.
