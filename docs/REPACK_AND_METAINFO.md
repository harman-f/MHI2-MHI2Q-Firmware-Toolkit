# Repack, metainfo2 and update-package reconstruction

The unpacking pipeline answers only half of the problem. Rebuilding an MHI2/MHI2Q update has four distinct layers:

1. **files** - modified files/directories or a complete extracted filesystem tree;
2. **filesystem image** - QNX6, IFS/ImageFS, EFS, MIFS Stage-2, Stage-1/EIFS wrappers;
3. **SWDL package tree** - RCC/MMX component directories plus metadata;
4. **transport/archive** - the directory copied to SD/USB or an archive used to distribute that directory.

Do not treat those layers as interchangeable.

## Preferred route for small/modular changes

For many research changes, rebuilding a full stock filesystem image is unnecessary. Harman SWDL metadata supports file/directory copy packages and optional final scripts. A package can therefore carry a bounded file payload and describe it in `metainfo2.txt`.

This is generally easier to audit than regenerating a 1+ GiB `app.img`, and it avoids claiming byte-exact image-builder support that this repository does not yet have.

## metainfo2.txt structure

Observed MHI2/MHI2Q files are INI-like but can contain repeated or legacy parser constructs that ordinary config writers do not preserve safely. `tools/metainfo2.py` therefore uses a conservative line-preserving parser rather than a generic INI serializer.

Commonly observed fields include:

- `release`, `MUVersion`, `vendor`, `variant*`, `region*`, `SupportedTrains`;
- `FinalScript`, `FinalScriptChecksum`, `FinalScriptMaxTime`;
- device/download-group sections;
- payload sections ending in `Application`, `Bootloader`, `File` or `Dir`;
- `FileName` or `Source`;
- `Destination`;
- `FileSize`;
- `CheckSum`, `CheckSum1`, `CheckSum2`, ...;
- `CheckSumSize` (524288 bytes is a common/default value in the reviewed public helper);
- `DeleteDestinationDirBeforeCopy`, `UpdateOnlyExisting`, `CheckType`;
- `MetafileChecksum`.

### Signed prefix / editable tail

A reviewed historical MHI2 hash helper treats everything through the final `signature*` line as the original signed prefix and recalculates payload metadata only in the appended tail.

`tools/metainfo2.py --mode auto` mirrors that boundary conservatively:

- if at least one `signature*` line exists, it selects `signed-tail`;
- bytes through the final signature line are kept unchanged;
- only sections after that boundary are considered for rewrite;
- `--mode full` must be selected explicitly when the complete file should be considered editable.

The report includes `signed_prefix_preserved` so callers can assert that boundary.

### Source resolution

Two common payload styles are handled:

- `FileName = "x.bin"`: resolve relative to the section path with its terminal role removed;
- `Source = "../../MARKER"`: resolve relative to the directory represented by the section path with its terminal role removed.

Paths escaping the supplied package root are rejected.

### Chunked file checksums

For `File`, `Application`, and `Bootloader` entries, the helper recalculates:

- `FileSize` = exact file length;
- SHA-1 independently for every `CheckSumSize` block;
- first block as `CheckSum`;
- additional blocks as `CheckSum1`, `CheckSum2`, ... .

If a modified file becomes shorter, stale numbered checksum entries are removed. A `CheckSumSize` of zero is treated as a single whole-file SHA-1. When the field is absent, the compatibility default is 524288 bytes.

### Dir / hashes.txt

For a `Dir` section, audit mode builds the expected `hashes.txt` **in memory** and reports the planned sidecar change. It does not mutate the package.

The generated file records each regular payload file with:

- `FileName`;
- `FileSize`;
- `CheckSumSize`;
- one or more `CheckSumN` SHA-1 values.

Existing leading blank/comment header text and LF/CRLF convention are preserved where possible. Directory `FileSize` is the sum of regular payload bytes plus the generated `hashes.txt` byte length, matching the behavior observed in the reviewed historical helper.

`--write` writes both the refreshed metainfo and any planned `hashes.txt` sidecars. `--output` deliberately refuses a metadata-only output when sidecars also need changes, because that would create an inconsistent package.

### FinalScript

When `FinalScript` resolves inside the package root, the helper refreshes its first/default SHA-1 block as `FinalScriptChecksum`, plans the parent directory `hashes.txt`, and refreshes the matching terminal `dir` section when present.

### Line endings

The helper reads and writes with newline preservation. In particular, a CRLF metainfo remains CRLF. This matters because metadata/hash behavior can depend on exact bytes.

### MetafileChecksum

For an editable `MetafileChecksum` entry the current model is:

`MetafileChecksum = SHA1(metainfo2.txt with the MetafileChecksum line removed)`

In signed-tail mode, an original `MetafileChecksum` inside the protected prefix is not rewritten.

The parser reports nonempty lines that are neither comments, sections nor key/value assignments. It never executes those lines.

## Legacy checksum-bypass behavior

Public MHI2 tooling and historical packages make use of flags such as:

- `skipMetaCRC = "true"`;
- `skipFileCopyCrc = "true"`;
- `skipCheckSignatureAndVariant = "true"`.

These are documented as **legacy SWDL behavior**, not as a security guarantee or a recommendation to disable validation. The helper does not add those flags automatically and does not generate command-injection payloads or append executable commands to checksum records.

If a supplied package already contains unusual trailing/parser content, the audit report preserves and flags it so the researcher can study the behavior manually.

## update.txt

A persisted SWDL transaction can contain an `update.txt`. Public MHI2 recovery documentation describes:

- `CRC` = CRC32 of all `update.txt` bytes **excluding the CRC line itself**, including line endings;
- `MetafileCRC` = the current `MetafileChecksum` value from `metainfo2.txt`;
- if the package intentionally has no `MetafileChecksum` and uses the legacy meta-CRC skip mode, `MetafileCRC = skip`.

Use `tools/update_txt.py` to audit or refresh only these integrity fields. It does not generate update transactions or device-specific TODO lists.

## Current image rebuild capability

| Image family | Extract | Rebuild in this repo | Current position |
|---|---:|---:|---|
| QNX6 `MMX2/app/.../app.img` | yes | **no** | Reader/materializer exists. A validated QNX6 writer preserving filesystem geometry/metadata is still required. |
| RCC root IFS | yes | **no** | A rebuild is theoretically possible with an authorized QNX `mkifs`-style toolchain plus an exact buildfile/metadata model; no round-trip writer is claimed here. |
| RCC/MMX EFS | yes | **no** | Reader exists via qnxmount; no validated EFS creator is integrated. |
| MIFS Stage 2 LZOZ | yes | **wrapper writer not validated** | Container framing is understood, but creating a new ImageFS and proving LZO1Z round-trip compatibility remains open. |
| Stage-1 / EIFS Android-style wrapper | yes | **wrapper-only concept** | Outer zlib/header format is understood; a rebuilt inner QNX startup/ImageFS still requires a validated image builder. |
| Quickboot | raw/analyze | **no** | Small selector/loader candidate; format and execution semantics are not sufficiently established to rewrite safely. |

Accordingly, a complete "extract tree -> edit -> rebuild every stock image -> flash" command would currently overstate what has been validated.

## Practical rebuild workflow today

For an authorized lab/unit and a small change:

1. start from a known package tree and preserve an immutable copy;
2. add or replace only the intended package payload;
3. run `tools/metainfo2.py metainfo2.txt --root .` in audit mode;
4. review every planned `FileSize`, `CheckSumN`, `hashes.txt`, signature-boundary and unresolved change;
5. run the same command with `--write` on the working copy;
6. run audit mode a second time and require no unexplained changes;
7. if an existing `update.txt` is part of the test fixture, refresh its integrity fields with `tools/update_txt.py`;
8. produce a distribution archive only after the unpacked package tree passes a second audit.

This toolkit deliberately stops short of vehicle flashing and device-specific recovery instructions.

## Historical helper comparison

The expanded implementation was behaviorally compared with an older `update-hashes.py` workflow that:

- used SHA-1 chunks controlled by `CheckSumSize`;
- regenerated `hashes.txt`;
- handled `File`, `Dir`, `Application` and `Bootloader`;
- handled `FinalScript`;
- preserved CRLF;
- split the editable area after the final `signature*` line.

The new implementation reproduces those observed format behaviors independently and adds audit-only planning, traversal checks, explicit signed-prefix assertions, deterministic tests, and no ConfigObj/six runtime dependency.

## Distribution archive

The head unit consumes the unpacked SWDL tree from supported media; a `.7z` or `.zip` used on a PC is primarily a distribution container. Recreating the archive does not make invalid SWDL metadata valid. Always validate the unpacked tree first.

## References

- Public MHI2 AIO/update templates: `harman-f/MHI2_MIB2_AIO_FW_Update_Template` and `Mr-MIBonk/M.I.B._More-Incredible-Bash`.
- Historical/public MIB wiki mirror: `LateAlways/mibwiki-mirror`, especially the `update.txt - FW update` page.
- Historical hash helper lineage: `alelec/mib2-update-hashes` (external; not vendored).
