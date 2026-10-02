# MHI2 firmware image layout and extraction guide

For the cross-family mental model covering MHI2, MHI2Q and MH2P layers, offset types and evidence levels, start with [`FIRMWARE_IMAGE_PRIMER.md`](FIRMWARE_IMAGE_PRIMER.md). This document intentionally remains the detailed MHI2-specific reference.

This document describes the layers an analyst encounters when unpacking MHI2
firmware, the formats currently observed in the retained MU1440/Audi K3663
fixtures, what the extraction code knows about them, and where evidence ends.
It is a parser-oriented guide, not a claim that every OEM, train, MU, or update
generation uses an identical layout.

## The layers: package → payload → wrapper → filesystem → files

```text
firmware update (.7z/.zip)
├── package metadata / version records
├── RCC (main control/compute domain)
│   ├── ifs-root*.ifs       bootable QNX Image Filesystem (IFS)
│   ├── ifs-emg*.ifs        emergency/recovery QNX IFS
│   └── efs-system*.efs     QNX Embedded Filesystem (EFS)
└── MMX2 (multimedia domain)
    ├── app/<variant>/app.img       QNX6 filesystem
    ├── efs-sys / efs-pers          QNX EFS images
    ├── mifs-stage1                 Android-style wrapper → QNX startup + ImageFS
    ├── eifs                        Android-style wrapper → QNX startup + ImageFS
    ├── mifs-stage2                 LZOZ block wrapper → QNX ImageFS → e.g. lsd.jxe
    └── qb-primary / qb-recovery    retained raw; boot-loader role is not yet proven
```

These names are archive member families seen in the inspected MU1440 package;
member names and directory spelling can vary. `.img`, `.ifs`, and `.efs` are
not enough to identify an encoding by themselves. The extractor classifies
from archive paths plus validated signatures/headers, then records the source
member and hashes in its manifest.

## Image-family reference

| Update member / evidence | Container and compression | Inner filesystem / content | Practical interpretation and limits |
| --- | --- | --- | --- |
| `RCC/ifs-root/.../ifs-root.ifs` | QNX IFS startup header (`EB 7E FF 00` on disk); observed RCC root payload is LZO-compressed | QNX ImageFS tree | Boot/root image for RCC. Current integrated extraction uses the pinned `dumpifs.py` parser and LZO support. Do not confuse its address within a raw RCC flash dump with QNX load/physical addresses in the startup header. |
| `RCC/ifs-emg/.../ifs-emergency.ifs` | QNX startup header; observed image payload is length-prefixed UCL/NRV2B blocks | QNX ImageFS | RCC emergency/recovery image. Internal bounded NRV2B framing/decoder and ImageFS parsing passed the MU1440 fixture; other QNX/HBCIFS variants remain unproven. |
| `RCC/efs-system/.../*.efs` | QNX EFS image, parsed through qnxmount in the current toolchain | EFS entries and metadata | Persistent RCC-side filesystem by package naming. Exact mount timing and target-specific policy should be read from the matching firmware configuration, not inferred from the suffix alone. |
| `MMX2/app/<50|70>/default/app.img` | Raw QNX6 filesystem; no outer Android/LZOZ wrapper observed | QNX6 directory/inode/block tree | Main MMX application filesystem. `/50/` and `/70/` are hardware/layout variants, not “old/new” labels that can safely be collapsed. The extracted trees retain per-entry hashes and symlink metadata. |
| `MMX2/efs-sys` and `MMX2/efs-pers` | QNX EFS variants; some are wrapped as image members but are recognized by the filesystem reader | EFS entries | MMX system/persistent areas. The package label is useful context; actual role is firmware-version-dependent. |
| `MMX2/mifs-stage2/.../mifs-stage2.img` | 0x200-byte header begins `LZOZ`; 32-bit little-endian output-block size and a table of compressed block lengths; payload starts at file offset 0x800; payload blocks use LZO1Z | Concatenated QNX ImageFS stream (observed decoded stream starts with `imagefs`) | Holds the later MIFS Java/LSD payload in inspected samples, including `ifs/lsd.jxe`. It is not itself an ordinary ZIP/JAR and the outer 0x800 payload offset is a format field/layout observation, not an IFS startup address. |
| `MMX2/mifs-stage1/...` and `MMX2/eifs/...` | Android-style eight-byte magic `A FF D FF O FF D FF`, 8 little-endian 32-bit header words, page-aligned zlib kernel payload | QNX startup image followed by QNX ImageFS | The wrapper's `page_size` and `kernel_size` bound the compressed kernel. The QNX startup header and ImageFS signature are then parsed inside the decompressed kernel. These are two nested formats, not an Android ext4 filesystem. |
| `MMX2/qb-primary` / `qb-recovery` | Opaque raw members in current extraction evidence | No filesystem tree claimed | Kept byte-for-byte with hashes. Embedded `KERNEL_PRIMARY`, `KERNEL_RECOVERY`, and `ANDROID!` strings support a boot-selection-loader hypothesis only; static markers do not prove execution behavior. |

Opaque members can be examined with `tools/binary_probe.py`. The probe records hashes, entropy, printable strings and offsets of known ELF/QNX/ImageFS/Android/Quickboot markers without executing or changing the input. A marker match remains evidence for follow-up analysis, not proof that a payload is safely rebuildable.
| `MMX2/img_ver.txt`, `metainfo2.txt`, similar records | Plain metadata/text | N/A | Firmware/package identity and selection context. Preserve beside images; useful for variant and provenance analysis. |

### QNX IFS startup header: file offsets are not load addresses

The QNX startup header carries fields including `header_size`, `startup_size`,
`stored_size`, `imagefs_paddr`, and `imagefs_size`. QNX documentation describes
the header as boot-loader/startup metadata and distinguishes the stored image
length from the uncompressed ImageFS length. In this repository's parsers:

- `EB 7E FF 00` identifies a candidate startup header in the byte stream;
- the header fields and source bounds are checked before treating it as valid;
- `startup_size` bounds the uncompressed startup portion before the image data;
- `stored_size` bounds the serialized image region when present in this variant;
- `imagefs_size` is the expected uncompressed filesystem byte count;
- `startup_vaddr` / `imagefs_paddr` are QNX memory/load addresses, **not** byte
  offsets where the image begins in a firmware archive or RCC dump.

An IFS may have a prefix before the startup header. The internal UCL IFS parser
therefore scans the source for the signature, validates plausible headers, and
uses the discovered file offset. It no longer assumes that the signature is
inside the first 64 KiB. If more than one structurally plausible startup header
is found, it stops with an ambiguity error rather than silently choosing the
first marker. This is intentional: a larger flash/partition dump may contain
multiple images and requires a selection rule based on provenance or image
identity.

The ImageFS is an image-contained filesystem (startup/kernel, boot scripts,
drivers and other files as built into that image), distinct from a writable
QNX EFS and from the QNX6 filesystem used by the MMX app image. Extracted
symlinks are recorded as metadata; the host export does not create live host
symlinks.

## RCC backup dumps and variable IFS-root Stage-2 positions

An update archive member such as `ifs-root.ifs` is not the same input as a full
backup `RCC_fs0.bin`. In an RCC dump, the compressed IFS-root Stage-2 image is
embedded at a location that varies by backup/firmware. A retained historical
backup workflow resolved the position dynamically in this order:

1. live `flashlock` result;
2. the backup's `*-ifs-root-part2-OFFSET.txt` sidecar;
3. scan the image for the QNX IFS start signature, then validate the candidate.

The historical backup corpus records five observed Stage-2 starts:

| Observed RCC dump offset | Sidecars in audited collection |
| --- | ---: |
| `0x00BA0000` | 557 |
| `0x00C20000` | 62 |
| `0x00BE0000` | 20 |
| `0x00BC0000` | 7 |
| `0x00C00000` | 6 |

Those are empirical corpus values, **not a complete address table or format
constant**. The legacy audit scripts use them to verify historical filename and
sidecar records; `reconstruct_backup_b.py` also has a fixed candidate table for
its narrowly scoped reconstruction. A reusable extractor must not promote
that table to a universal parser rule. Likewise, the observed fixed Stage-2
region end `0x1D40000` is evidence from that backup set, not guaranteed for
every train or dump format.

The current firmware-archive extractor parses a standalone IFS member. It does
not yet expose a general “scan a whole RCC_fs0 and enumerate/carve every valid
IFS candidate” command. The new startup-marker scan prepares the parser for
variable offsets but deliberately rejects multiple valid candidates. A future
RCC-dump mode should enumerate candidates and report for each: byte offset,
header version/flags, compression type, `startup_size`, `stored_size`,
`imagefs_size`, consumed span, hashes, and validation status. It should prefer
live/sidecar evidence when supplied, use marker scanning as fallback, preserve
the source unchanged, and stop on ambiguity unless the user selects a candidate.
Never carve a length from a fixed region-end assumption when validated header
lengths and source bounds are available.

## Compression and extraction pipeline

```text
7z/ZIP inventory
  → preserve selected raw update members + source/member hashes
  → identify wrapper from validated magic/header (not extension alone)
  → decode outer compression/container with declared bounds
  → locate/validate QNX startup or ImageFS structure
  → parse filesystem metadata and file entries
  → write files additively; represent symlinks/duplicates in metadata
  → hash outputs and emit manifest / freeze ledger on failure
```

Do not conflate these compression layers:

- QNX IFS can carry an uncompressed startup section and a separately compressed
  ImageFS payload; compression type comes from QNX startup flags.
- The audited RCC emergency image uses UCL/NRV2B framing in 64-KiB expanded
  blocks. The code validates per-block lengths and total `imagefs_size`.
- The MIFS Stage-2 `LZOZ` header wraps length-table-selected LZO1Z blocks; its
  output is a QNX ImageFS stream.
- The Stage-1/EIFS Android-style wrapper contains a zlib-compressed kernel;
  inside it the QNX startup header leads to an ImageFS region.
- QNX6 app and EFS readers parse filesystem-native structures rather than
  applying one of the preceding whole-image decompressors.

## Evidence, portability and questions to keep open

The detailed parser/test coverage and exact sample hashes are summarized in
[`../reports/MHI2_FIRMWARE_EXTRACTION_TOOLING_AUDIT_2026-09-28.md`](../reports/MHI2_FIRMWARE_EXTRACTION_TOOLING_AUDIT_2026-09-28.md).
Implementation boundaries and dependency pins are in
[`../DEPENDENCIES.md`](../DEPENDENCIES.md). The full test MU1440 archives and
expanded trees remain `LOCAL-ONLY`; only code, synthetic parser fixtures,
reports and hashes are intended for this repository.

For a future transplant into a standalone extraction repository, keep this
format guide alongside the tools and include at least:

- format/member inventory with train, MU, source archive hash, member size and
  extraction status;
- startup-marker candidate reports, not only a final carved file;
- per-filesystem entry counts, hashes, symlink targets and duplicate-name
  policy;
- separate raw, decoded-image, filesystem-tree and Java/decompilation layers;
- which facts are format-level, which were observed only in MU1440/K3663, and
  which remain hypotheses (especially quickboot and exact runtime ownership of
  the EFS regions);
- malformed/truncated fixtures and variable-prefix/multiple-candidate tests.


## Deeper flash-layout and recovery evidence

For exact sample byte sizes/signatures, historical MMX NOR offset tables, the limited RCC address evidence, and boot-chain/recovery boundaries, see [`MHI2_FLASH_LAYOUT_AND_RECOVERY.md`](MHI2_FLASH_LAYOUT_AND_RECOVERY.md). Its tables distinguish measured MU1440 archive bytes from wiki-reported physical flash offsets; neither is presented as a universal layout.

## References

- QNX, [Image Filesystem (IFS)](https://qnx.com/developers/docs/7.1/com.qnx.doc.neutrino.building/topic/intro/intro_ifs.html).
- QNX, [startup header fields](https://www.get.qnx.com/developers/docs/7.0.0/com.qnx.doc.neutrino.building/topic/ipl/ipl_startup_header.html).
- QNX, [`dumpifs`](https://qnx.com/developers/docs/6.5.0SP1.update/com.qnx.doc.neutrino_utilities/d/dumpifs.html) and [`mkifs`](https://qnx.com/developers/docs/6.5.0SP1.update/com.qnx.doc.neutrino_utilities/m/mkifs.html).
- Historical private audit scripts were reviewed for backup-offset evidence. They are not distributed here, and their fixed offset tables are not copied as general format constants.


## Relationship to MH2P / Alpine

Do not copy the MHI2 package tree onto MH2P by name. The validated MH2P/Alpine sample uses
`Data/MMX2P.*` members and an `LZ4_` segmented Stage-2 path rather than the MHI2
`MMX2/.../mifs-stage2` `LZOZ` container. Some inner QNX/ImageFS concepts are reusable,
but package routing and container semantics are separate evidence questions.

For the current MH2P support boundary and commands, see
[`MH2P_GUIDE.md`](MH2P_GUIDE.md). For the common package -> wrapper -> filesystem model,
see [`FIRMWARE_IMAGE_PRIMER.md`](FIRMWARE_IMAGE_PRIMER.md).
