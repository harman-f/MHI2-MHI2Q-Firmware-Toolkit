# Detailed MU1440 firmware extraction baseline audit — 2026-09-28

## Summary

The source toolkit passed a complete MU1440 archive extraction test. This report preserves the detailed MU1440 measurements; broader multi-OEM validation is summarized separately in `MULTI_FIRMWARE_VALIDATION_2026-09-28.md`. This repository does not contain firmware archives or extracted filesystem outputs.

Test source: Škoda MHI2 ER SKG13 P4526 MU1440 archive, SHA-256 `b23225d68999f0613f2652c898ce36c74d6c1d63a36f29ff5d4faf500c60e5a5`. The archive and output remain local-only. No firmware bytes were copied into this repository.

The integrated run selected and hash-verified 29 archive members totaling 3,051,937,361 bytes. It parsed the tested MMX app variants, RCC root/EFS, MMX EFS, MIFS Stage 2, Stage 1, EIFS, and RCC Emergency IFS. Quickboot members were kept raw and classified only from path/embedded-marker evidence; execution was not dynamically tested. LSD JXE was successfully exported; JXE-to-JAR/Java conversion is deliberately external post-processing rather than an integrated dependency.

## Observed results

| Component | MU1440 baseline result |
|---|---|
| MMX2 app /50/ | 5,232 files; 1,034 symlinks; 736,111,706 regular bytes |
| MMX2 app /70/ | 5,334 files; 1,034 symlinks; 822,645,100 regular bytes |
| RCC root IFS | 193 regular files / 14,949,243 bytes; 33 symlinks; duplicate source path retained in metadata |
| RCC EFS | 156 files; 24,695,974 bytes |
| MMX EFS persist /50/ and /70/ | Each 2 files; 419,140 bytes |
| MMX EFS system /50/ and /70/ | Each 209 files; 2 symlinks; 1,061,278 bytes |
| MIFS Stage 2 /50/ and /70/ | Each 319 entries (215 files, 91 symlinks, 13 directories); 75,241,662 materialized bytes |
| MMX Stage 1 /50/ and /70/ | Each 114 entries |
| MMX EIFS | 171 entries |
| RCC Emergency IFS | 133 entries; 7,520,811 materialized bytes |
| Quickboot primary/recovery | 102,431 bytes each; byte-identical in the measured sample; raw/opaque analysis only |

Both Stage-2 variants decoded to the same 75,529,244-byte ImageFS stream (SHA-256 `4456de46a33e3731da95ef386da035e43990037fe9ccaeea171657732e8cddb1`). Emergency IFS decoded to 9,035,508 bytes (SHA-256 `16df74fd9ad18fbcf9cda0facd4f8a8228b715e09f01267adedc4910ba50738d`). The internal NRV2B decoder was differentially checked against Binary Refinery 0.11.2 for all 138 observed blocks.

A previous RCC-root export differs by 10,400 bytes due to two source records for `usr/bin/setconf`; both are retained in metadata. QNX runtime name-resolution behavior is not established by this comparison.

## Verification in this repository

The repository now includes the original parser tests plus synthetic tests for metainfo refresh, update.txt CRC handling and opaque-binary probing. CI also compiles all Python sources before running the unit suite.

    python -m unittest discover -s tests -v

The synthetic/unit suite does not replace the local firmware corpus integration run.

## Boundaries and remaining work

- External provisioning for 7-Zip, qnxmount, dumpifs, and LZO is not packaged as a reproducible offline bundle.
- `python-lzo` is GPL-2.0-only and imported in-process. Resolve compatibility with the repository's GPL-3.0-only license before distributing a combined environment.
- JXE-to-JAR conversion is not bundled. `lsd.jxe` is exported and external workflows are documented in `docs/EXTERNAL_TOOLS.md`.
- Multi-OEM MHI2 validation now includes Audi, Škoda, Volkswagen and SEAT, including G11/G13-family trains; see `MULTI_FIRMWARE_VALIDATION_2026-09-28.md`.
- MHI2Q has not yet received equivalent full-corpus extraction validation and remains an explicit coverage target.
- No complete QNX6/IFS/EFS image writer or vehicle flashing capability is claimed. The reverse/repack boundary is documented in `docs/REPACK_AND_METAINFO.md`.
- Quickboot and other opaque payloads can now be probed statically, but a byte-level quickboot format/parser is not yet established.
- Emergency IFS and Stage-2 parsing now have broader MHI2 corpus coverage, but additional structurally distinct firmware families and MHI2Q samples remain useful validation targets.

See [the image layout guide](../docs/MHI2_IMAGE_FORMATS_AND_LAYOUT.md), [repack guide](../docs/REPACK_AND_METAINFO.md), and [dependency inventory](../DEPENDENCIES.md).
