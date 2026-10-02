# Firmware image primer

This document is the cross-family mental model for the toolkit. It explains how to
reason about MHI2, MHI2Q and MH2P firmware artifacts before choosing a parser.

The most important rule is simple: a firmware "image" is often only one layer in a
stack. A filename such as `.img`, `.ifs` or `.bin` does not identify the format by
itself.

## The layers

A typical analysis moves through several distinct layers:

```text
distribution archive
  -> SWDL/package tree and metadata
    -> component payload
      -> wrapper / compression / boot container
        -> filesystem or boot image
          -> files / classes / executables
            -> runtime interpretation
```

Treat every arrow as a separate decoding step. Keep the original bytes and the decoded
bytes distinguishable in manifests and reports.

### 1. Distribution archive

Usually a PC-side `.7z` or `.zip`. It groups the update package but is not the format
the head unit ultimately executes.

Questions to ask:

- What is the exact source SHA-256?
- Which package root is selected?
- Which OEM/train/MU does the metadata identify?
- Are there multiple hardware variants such as `/50/` and `/70/`?

### 2. SWDL/package tree

This is the firmware update's logical component structure: RCC, MMX/MMX2, metadata,
Stage-1/Stage-2, EFS, app images and similar members.

Package paths are useful evidence, but they are not sufficient to identify the bytes.
A member called `app.img` can be a filesystem image while another `.img` is a compressed
boot container.

### 3. Component payload

This is the exact member selected from the package. Always hash it before interpretation.
The same logical role can have different wrappers across platform families or trains.

### 4. Wrapper / compression / boot container

Examples seen by this toolkit include:

- QNX IFS startup structures;
- QNX EFS;
- raw QNX6 filesystems;
- Android-style wrapper headers carrying compressed QNX content;
- MHI2 `LZOZ` Stage-2 block containers;
- MH2P/Alpine `LZ4_` segmented Stage-2 containers.

A valid magic value is only the start of validation. Length fields, offsets, block
consumption, padding, checksums and source bounds also need to agree.

### 5. Filesystem or boot image

Common inner structures are QNX6, QNX EFS and QNX ImageFS. These are different
formats with different metadata and should not be treated as interchangeable merely
because they all belong to QNX-based firmware.

### 6. Materialized files

Only after the inner filesystem has been validated should regular files be exported.
Symlinks and unusual node types are recorded as metadata instead of being blindly
recreated on the host.

### 7. Runtime interpretation

Finding an ELF, JAR, JXE or script does not by itself prove when it runs, what loads it,
or which hardware owns it. Runtime conclusions require additional evidence from startup
scripts, configuration, symbol/call analysis, logs or dynamic observation.

## Five different kinds of "offset"

Firmware work becomes confusing when different address spaces are mixed together. Keep
these separate:

| Value | Meaning |
|---|---|
| Archive/member offset | Byte position inside a package member or container |
| Decoded-stream offset | Byte position after decompression/decoding |
| Filesystem logical offset | Position of a file or extent inside a filesystem image |
| Flash/device offset | Physical or partition-relative location on NOR/NAND/eMMC |
| Load/virtual/physical address | Address used by the CPU/boot process at runtime |

A QNX startup header can contain load addresses while the same image occurs at a completely
different byte offset in a firmware archive or flash dump. Never substitute one for the
other without evidence.

## MHI2 / MHI2Q topology

A simplified observed MHI2-style package looks like:

```text
firmware archive
├─ metadata
├─ RCC
│  ├─ ifs-root            -> QNX IFS -> ImageFS
│  ├─ ifs-emergency       -> QNX startup/compression -> ImageFS
│  └─ efs-system          -> QNX EFS
└─ MMX2
   ├─ app/<variant>       -> QNX6 filesystem
   ├─ efs-sys / efs-pers -> QNX EFS
   ├─ mifs-stage1 / eifs  -> wrapper -> compressed QNX startup -> ImageFS
   ├─ mifs-stage2         -> LZOZ -> ImageFS -> e.g. lsd.jxe
   └─ qb-*                -> opaque/raw unless separately proven
```

The detailed MHI2 evidence, signatures and sample-specific limitations are in
`MHI2_IMAGE_FORMATS_AND_LAYOUT.md`.

## MH2P / Alpine topology

The validated MH2P sample uses a different package naming/layout model, including
`Data/MMX2P.*` members. The reusable idea is not "MH2P equals MHI2"; it is that some
inner formats are shared or similar enough to reuse strict QNX/ImageFS readers.

A simplified evidence-driven view is:

```text
MH2P/Alpine archive
├─ Data/MMX2P.app_*        -> QNX6 app filesystem
├─ Data/MMX2P.efs-*        -> QNX EFS
├─ Data/MMX2P.mifs-stage2  -> LZ4_ segmented container
│                            -> decoded stream
│                              -> ImageFS images
│                                -> JAR/JXE and system content
└─ boot / Quickboot / other members
                             -> retain raw unless format is proven
```

The public MH2P Stage-2 tooling is intentionally bounded. Current family-level claims are
based on one strong VW G36 P2838 validation baseline, so another train must be treated as
a new validation exercise.

## Why extensions and strings are insufficient

Do not classify a binary solely because:

- its suffix is `.img`, `.ifs`, `.efs` or `.bin`;
- a known ASCII marker appears somewhere inside it;
- 7-Zip happens to open a nested region;
- one offset matches a historical sample;
- one firmware from the same platform decoded successfully.

A stronger classification combines path/provenance with structural validation and
declared bounds.

## Evidence ladder

Use these labels mentally when making claims:

1. **Marker evidence** — magic/string/path suggests a format or role.
2. **Structural evidence** — headers, bounds and internal fields validate.
3. **Decode evidence** — wrapper/compression decodes completely within declared limits.
4. **Filesystem evidence** — a strict reader inventories/materializes the inner image.
5. **Cross-check evidence** — hashes, independent parser/library checks or repeated copies agree.
6. **Corpus evidence** — the same behavior is reproduced across multiple independent firmware baselines.

Do not promote level 1 or 2 evidence into a family-wide support claim.

## Practical decision tree for a new artifact

```text
Do I know the exact source/package identity?
  no -> establish provenance + SHA-256 first
  yes
    |
Is it a supported archive?
  yes -> run extract_firmware.py --plan
  no
    |
Is it a known raw image type?
  yes -> use the matching extractor/parser
  no
    |
Run binary_probe.py
    |
Do validated magic + lengths identify a known wrapper/filesystem?
  yes -> use the narrow parser and preserve hashes
  no  -> keep it opaque and document the evidence gap
```

For a new MH2P Stage-2 image, use the MH2P-specific workflow in `MH2P_GUIDE.md`.

## Extraction versus rebuild

Being able to extract a format does not imply the repository can rebuild it byte-for-byte.
The current toolkit has good read-side coverage for several image families but deliberately
does not claim general QNX6/IFS/EFS image writers or a complete stock-image round trip.

For package metadata reconstruction, use `metainfo2.py` and `update_txt.py` as described
in `REPACK_AND_METAINFO.md`. For actual filesystem-image rebuilding, treat the capability
matrix there as authoritative.

## Cross-family portability rule

When code or a parser appears reusable across MHI2, MHI2Q and MH2P:

- reuse the generic reader only if the bytes satisfy the same validated invariants;
- keep package routing and train-specific assumptions separate;
- record the exact firmware sample that confirmed the path;
- do not rename sample-specific behavior into a universal format rule;
- add synthetic malformed/truncated tests before broadening support.

This is the core distinction between reusable format knowledge and platform folklore.
