# Multi-firmware extraction validation — 2026-09-28

## Scope

The current extraction implementation was exercised end-to-end against six independently identified MHI2 firmware archives spanning four OEMs and several train families. The validated extractor code revision is:

`c87f743655211e7fe71180a86d9c23f6f9149fd7`

Later publication-only documentation changes do not alter the extractor/parser implementation covered by this matrix.

Every run used source-hash admission, `--plan`, both 50/70 variants where present, and full selected MMX/RCC materialization. Raw archives and complete extracted trees are not distributed by this repository.

## Firmware matrix

| OEM | Firmware | MU | Family/train | Selected members | Selected bytes | Result |
|---|---|---:|---|---:|---:|---|
| Audi | `MHI2_ER_AUG22_K3346` | 1438 | AUG22 | 29 | 1,944,285,314 | Selected filesystems exported; only Quickboot primary/recovery retained opaque |
| Škoda | `MHI2_ER_SKG13_P4526` | 1440 | SKG13 | 29 | 3,051,937,361 | Selected filesystems exported; only Quickboot primary/recovery retained opaque |
| Škoda | `MHI2_ER_SKG11_K3343` | 1433 | SKG11 | 29 | 1,944,230,216 | Selected filesystems exported; only Quickboot primary/recovery retained opaque |
| Volkswagen | `MHI2_ER_VWG11_K3342` | 1427 | G11 | 29 | 1,944,224,855 | Selected filesystems exported; only Quickboot primary/recovery retained opaque |
| SEAT | `MHI2_ER_SEG11_P4709` | 1447 | SEG11 | 29 | 1,944,520,253 | Selected filesystems exported; nested archive prefix handled; only Quickboot primary/recovery retained opaque |
| Volkswagen | `MHI2_ER_VWG13_K4525` | 1367 | G13 | 29 | 3,051,958,407 | Selected filesystems exported; only Quickboot primary/recovery retained opaque |

The toolkit reports these runs as `PARTIAL` because Quickboot is intentionally retained as raw/opaque evidence instead of being falsely classified as a parsed filesystem. For the supported selected filesystem/image families, materialization completed successfully.

## Independent output audit

A separate post-extraction verification rehashed every materialized regular file across all six baselines:

- expected/materialized files checked: **74,574 / 74,574**;
- SHA-256 mismatches: **0**;
- missing files: **0**;
- unexpected extra files: **0**.

This independently validates that the committed inventory and the files written to disk agree for the six-run corpus.

## Stage-2 reference checks

Two reference trains received additional byte-level Stage-2 checks.

### Audi AUG22 K3346 MU1438

- decoded ImageFS /50 and /70: 76,041,000 bytes each;
- decoded SHA-256 for both variants: `34fe05b0b53b945bf316825139ba098fb7d3babbc15ef7d96aec9eb6a47650c8`;
- selected `lsd.jxe`: 58,131,096 bytes;
- JXE SHA-256: `e43d80e7eeb803d6a7db29908562b9545e7b17138d4660ce3a6efafa974b99ce`.

### Škoda SKG13 P4526 MU1440

- decoded ImageFS /50 and /70: 75,529,244 bytes each;
- decoded SHA-256 for both variants: `4456de46a33e3731da95ef386da035e43990037fe9ccaeea171657732e8cddb1`;
- selected `lsd.jxe`: 55,840,933 bytes;
- JXE SHA-256: `a55d9cfb69c5756f8202b7f7aa4079d4d5b637ae4c2fd0fe723f1d6816cbeea8`.

## Regression and native-analysis checks

At the validated toolkit revision:

- the source test suite passed **58 tests**;
- the corrected MIFS Stage-2 parser includes a two-block regression where an already sector-aligned compressed block must not advance by an extra sector;
- manifest generation records the pinned qnxmount revision;
- 12 targeted native-analysis inputs completed with zero exporter failures during the associated corpus audit.

## Boundaries

This matrix validates multiple MHI2 OEM/train combinations. It does **not** establish universal compatibility, vehicle runtime behavior, patch safety, or permission to redistribute firmware.

MHI2Q remains in project scope but has not yet received the same full-corpus extraction validation. Unknown or unsupported binary formats must remain raw/opaque rather than being inferred as parsed.

For JXE-to-JAR conversion and firmware-to-firmware Java comparison, the preferred external baseline is `luka-dev/jxe2jar` at the pin documented in `docs/EXTERNAL_TOOLS.md`; it is not bundled in this repository.
