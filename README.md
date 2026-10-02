# MHI2 / MHI2Q Firmware Toolkit

A host-side toolkit for inventorying MHI2-family firmware packages, exporting RCC/MMX components into reviewable directory trees, auditing opaque binary payloads, and reconstructing supported SWDL metadata. Firmware archives and generated exports are user-supplied data and are deliberately not part of this repository.

**Project license:** GNU GPL-3.0-only for project-authored code and documentation unless an individual file or notice states otherwise. See `LICENSE` and `DEPENDENCIES.md`.

## Current status

The extraction implementation has been exercised end-to-end against six MHI2 firmware baselines spanning Audi, Škoda, Volkswagen and SEAT, including AUG22, G11/G13-family trains and both 50/70 variants. All selected MMX/RCC filesystems materialized successfully; the only intentional `PARTIAL` classification is the pair of raw Quickboot payloads, which remain opaque by design. An independent post-extraction rehash verified 74,574/74,574 materialized files with zero missing, extra or mismatched files. See `reports/MULTI_FIRMWARE_VALIDATION_2026-09-28.md` and the detailed MU1440 baseline audit.

This validation is substantial MHI2 coverage, not a claim of universal compatibility. MHI2Q remains within the toolkit's intended scope but has not yet received the same full-corpus extraction validation.

Current parsing paths include QNX6 MMX app/EFS trees (external qnxmount), RCC root IFS (external dumpifs + LZO), RCC/MMX MIFS Stage 2, Android-style Stage 1/EIFS modules, Emergency IFS, and metadata-only symlink preservation. Unknown image/binary payloads remain byte-exact and can be inspected with the read-only binary probe rather than being misrepresented as parsed filesystems.

## Quick start

Requirements vary by selected component: Python 3.10+, 7-Zip for firmware archives, and separately provisioned qnxmount, dumpifs, and LZO support for paths that need them. Start with `DEPENDENCIES.md`; this is not a self-contained offline bundle.

Windows PowerShell:

    python .\tools\extract_firmware.py --source .\firmware\update.7z --output .\exports\mhi2-r1 --plan
    python .\tools\extract_firmware.py --source .\firmware\update.7z --output .\exports\mhi2-r1 --component rcc --component mmx

Linux / WSL / Git Bash menu:

    bash tools/mhi2-extract.sh

Non-interactive example:

    bash tools/mhi2-extract.sh --source ./firmware/update.7z --output ./exports/mhi2-r1 --component mmx

Output directories must be new and nonexistent. Failed extractions preserve partial state and emit a freeze ledger; the tool does not clean up or overwrite a previous export. Review the resulting manifest and image metadata before relying on an export. Symlinks are represented as metadata, not created as host links.

## Selective modes

Repeat `--component` to combine `rcc`, `mmx`, and `java`. The `java` component exports Stage 2 and the LSD JXE source file. JXE-to-JAR/Java decompilation is intentionally external. For new JXE conversion and firmware-to-firmware Java comparisons, the preferred route is `luka-dev/jxe2jar`; `JeniCzech92/lsdtool` remains a clearly licensed known-working alternative. See `docs/EXTERNAL_TOOLS.md` for exact pins, licensing notes, CFR, Ghidra and QNX ARM tooling.

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

- `tools/`: extractor, bounded parsers, metadata/repack helpers, binary probe, Bash host menu.
- `tests/`: synthetic/unit tests; no firmware images required.
- `docs/MHI2_IMAGE_FORMATS_AND_LAYOUT.md`: image/container layout and extraction model.
- `docs/MHI2_FLASH_LAYOUT_AND_RECOVERY.md`: measured image sizes/start bytes, historical address evidence and recovery boundaries.
- `docs/REPACK_AND_METAINFO.md`: reverse/package reconstruction model and current rebuild capability matrix.
- `docs/EXTERNAL_TOOLS.md`: external Java, Ghidra and QNX toolchains.
- `reports/`: multi-firmware validation matrix, detailed MU1440 baseline audit, and explicit limitations.
- `DEPENDENCIES.md`: provenance, license status, and packaging boundaries.

Run tests with:

    python -m unittest discover -s tests -v


## Safety and scope

The extractor reads source archives/images and only writes to a requested new output directory. Metadata refresh helpers are host-side file transformations and default to audit-only behavior unless an explicit output/write option is supplied. The repository does not flash firmware or perform vehicle-side writes.

Firmware and derived filesystem data stay outside Git; `.gitignore` blocks common firmware/archive extensions as a safeguard, not as a substitute for reviewing `git status`.

The current integration corpus validates multiple MHI2 OEM/train combinations; MHI2Q and additional platforms remain coverage-expansion targets until equivalent corpus evidence exists. Contributions should prefer small redistributable synthetic fixtures. Do not commit proprietary firmware data without a separate explicit review.

## Preferred external LSD/JXE workflow

For new `lsd.jxe -> JAR` conversion, class-set comparison and firmware-to-firmware Java analysis, use `luka-dev/jxe2jar` as the preferred external baseline at the pinned revision documented in `docs/EXTERNAL_TOOLS.md`. It is not bundled or redistributed here because no clear top-level license grant was found at the reviewed pin. `JeniCzech92/lsdtool` remains a useful MIT-licensed known-working alternative and cross-check.
