# MHI2 / MHI2Q / MH2P Firmware Toolkit

A host-side toolkit for inventorying MHI2/MHI2Q firmware packages and bounded MH2P/Alpine inputs, exporting supported components into reviewable directory trees, auditing opaque binary payloads, and reconstructing supported SWDL metadata. Firmware archives and generated exports are user-supplied data and are deliberately not part of this repository.

**Project license:** GNU GPL-3.0-only for project-authored code and documentation unless an individual file or notice states otherwise. See `LICENSE` and `DEPENDENCIES.md`.

## Current status

The extraction implementation has been exercised end-to-end against six MHI2 firmware baselines spanning Audi, Škoda, Volkswagen and SEAT, including AUG22, G11/G13-family trains and both 50/70 variants. All selected MMX/RCC filesystems materialized successfully; the only intentional `PARTIAL` classification is the pair of raw Quickboot payloads, which remain opaque by design. An independent post-extraction rehash verified 74,574/74,574 materialized files with zero missing, extra or mismatched files. See `reports/MULTI_FIRMWARE_VALIDATION_2026-09-28.md` and the detailed MU1440 baseline audit.

This validation is substantial MHI2 coverage, not a claim of universal compatibility. MHI2Q remains within the toolkit's intended scope but has not yet received the same full-corpus extraction validation. MH2P/Alpine is also in scope, but the current evidence is deliberately narrower: one VW G36 P2838 firmware baseline was exercised successfully and is treated as a strong single-sample validation, not as proof of cross-train compatibility.

### Capability / evidence matrix

| Family | Published support level | Validation evidence | Claim boundary |
|---|---|---|---|
| MHI2 | Stable core | Six firmware baselines across multiple OEM/train combinations | Broadly exercised, not universal |
| MHI2Q | Intended core scope | Less corpus coverage than MHI2 | Validate each train before relying on portability |
| MH2P / Alpine | Experimental / bounded | One VW G36 P2838 baseline exercised successfully | Do not generalize one successful firmware to all MH2P trains |

For a tool-by-tool operational guide, including inputs, outputs, dependencies, failure behavior and example commands, see `docs/TOOL_GUIDE.md`. For the MH2P evidence boundary and the recommended workflow, see `docs/MH2P_GUIDE.md`.

Current stable parsing paths include QNX6 MMX app/EFS trees (external qnxmount), RCC root IFS (external dumpifs + LZO), RCC/MMX MIFS Stage 2, Android-style Stage 1/EIFS modules, Emergency IFS, and metadata-only symlink preservation. Unknown image/binary payloads remain byte-exact and can be inspected with the read-only binary probe rather than being misrepresented as parsed filesystems. Bounded MH2P/Alpine `LZ4_` Stage-2 probes are available separately under `tools/experimental/`; they are intentionally partial and do not imply general MH2P support.

## Quick start

Requirements vary by selected component: Python 3.10+, 7-Zip for firmware archives, and separately provisioned qnxmount, dumpifs, LZO, or LZ4 support for paths that need them. Start with `docs/TOOL_GUIDE.md` to choose the right entry point, then `DEPENDENCIES.md`; this is not a self-contained offline bundle.

Windows PowerShell:

    python .\tools\extract_firmware.py --source .\firmware\update.7z --output .\exports\mhi2-r1 --plan
    python .\tools\extract_firmware.py --source .\firmware\update.7z --output .\exports\mhi2-r1 --component rcc --component mmx

Linux / WSL / Git Bash menu:

    bash tools/mhi2-extract.sh

Non-interactive example:

    bash tools/mhi2-extract.sh --source ./firmware/update.7z --output ./exports/mhi2-r1 --component mmx

Output directories must be new and nonexistent. Failed extractions preserve partial state and emit a freeze ledger; the tool does not clean up or overwrite a previous export. Review the resulting manifest and image metadata before relying on an export. Symlinks are represented as metadata, not created as host links.

## Selective modes

Repeat `--component` to combine `rcc`, `mmx`, and `java`. The `java` component exports Stage 2 and the LSD JXE source file. JXE-to-JAR conversion remains external-code execution: `tools/jxe2jar/convert-jxe.ps1` checks out the reviewed `luka-dev/jxe2jar` commit `9eeb45bbf14bf8afe3452c7be96a4d1f0206a286`, verifies the checkout, converts the JXE, validates the JAR, and records hashes. Upstream code is not vendored. `JeniCzech92/lsdtool` remains a clearly licensed historical cross-check. See `docs/EXTERNAL_TOOLS.md`.

Use `--variant auto|50|70|both`, `--expected-sha256`, and `--plan` to constrain or inspect runs.

## Opaque/raw binary analysis

For raw members such as Quickboot or an unrecognized DSP image:

    python tools/binary_probe.py path/to/qb-primary.img --output qb-primary.analysis.json

The probe records SHA-256, byte length, entropy, bounded printable strings and offsets of known container/boot markers. It does not execute or modify the binary.

## Repack / reverse direction

The toolkit includes conservative helpers for rebuilding the metadata side of a package:

    python tools/metainfo2.py path/to/metainfo2.txt --root path/to/package
    python tools/metainfo2.py path/to/metainfo2.txt --root path/to/package --write
    python tools/update_txt.py path/to/update.txt --metainfo path/to/metainfo2.txt --output refreshed-update.txt

Audit mode is the default. `metainfo2.py` understands chunked `CheckSum`/`CheckSumN` SHA-1 values, `File`/`Application`/`Bootloader`/`Dir` sections, planned `hashes.txt` regeneration, FinalScript metadata, LF/CRLF preservation, and the historical signed-prefix/editable-tail boundary after the last `signature*` line. Sidecar files are only changed with `--write`. It never executes unknown metainfo lines or adds checksum-bypass flags.

A full extracted-filesystem-to-stock-image rebuild is **not** yet claimed. QNX6/IFS/EFS writers and exact round-trip image geometry remain separate work. See `docs/REPACK_AND_METAINFO.md`.

## Contents

- `tools/`: stable extractor, bounded parsers, metadata/repack helpers, binary probe, Bash host menu.
- `tools/jxe2jar/`: commit-pinned wrapper for the preferred external JXE converter.
- `tools/experimental/`: explicitly partial MH2P/Alpine Stage-2 probes.
- `tests/`: synthetic/unit tests; no firmware images required.
- `docs/FIRMWARE_IMAGE_PRIMER.md`: cross-family theory for package/container/filesystem layers, offsets, evidence levels and parser selection.
- `docs/TOOL_GUIDE.md`: human- and agent-oriented tool catalog, decision flow, inputs/outputs, dependencies and examples.
- `docs/AGENT_PLAYBOOK.md`: use-case recipes such as unpack, Java/LSD, comparison, unknown images, MH2P and package rebuild.
- `docs/MH2P_GUIDE.md`: MH2P/Alpine validation boundary and bounded Stage-2 workflow.
- `docs/MHI2_IMAGE_FORMATS_AND_LAYOUT.md`: image/container layout and extraction model.
- `docs/MHI2_FLASH_LAYOUT_AND_RECOVERY.md`: measured image sizes/start bytes, historical address evidence and recovery boundaries.
- `docs/REPACK_AND_METAINFO.md`: reverse/package reconstruction model and current rebuild capability matrix.
- `docs/EXTERNAL_TOOLS.md`: external Java, Ghidra and QNX toolchains.
- `reports/`: validation reports, limitations, and the 2026-10-02 public migration/toolchain audit.
- `DEPENDENCIES.md`: provenance, license status, and packaging boundaries.

Run tests with:

    python -m compileall -q tools tests
    python -m unittest discover -s tests -v

CI runs the suite on Python 3.10 and 3.12, includes public-repository hygiene checks, and runs CodeQL on `main` and pull requests.


## Safety and scope

The extractor reads source archives/images and only writes to a requested new output directory. Metadata refresh helpers are host-side file transformations and default to audit-only behavior unless an explicit output/write option is supplied. The repository does not flash firmware or perform vehicle-side writes.

Firmware and derived filesystem data stay outside Git; `.gitignore` blocks common firmware/archive extensions as a safeguard, not as a substitute for reviewing `git status`.

The current integration corpus validates multiple MHI2 OEM/train combinations. MHI2Q remains a coverage-expansion target. MH2P/Alpine has one strong end-to-end validation baseline (VW G36 P2838), but one sample is not treated as family-wide compatibility evidence. Contributions should prefer small redistributable synthetic fixtures. Do not commit proprietary firmware data without a separate explicit review.

## Preferred external LSD/JXE workflow

For new `lsd.jxe -> JAR` conversion and Java-analysis baselines, use `luka-dev/jxe2jar` at the exact reviewed pin documented in `docs/EXTERNAL_TOOLS.md`. The project-authored wrapper in `tools/jxe2jar/` fetches that external revision without vendoring it. The previously documented `3bae6e…` pin is no longer treated as current; the 2026-10-02 reviewed pin is `9eeb45bb…`. `JeniCzech92/lsdtool` remains a useful MIT-licensed historical cross-check.
