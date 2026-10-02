# Tool guide

This guide is the operational index for humans and AI agents. Use it to decide which
entry point fits a task before reading implementation code. If the image/container model
is unclear, read `FIRMWARE_IMAGE_PRIMER.md` first. For task-oriented recipes such as
"compare two firmwares" or "I only need LSD", see `AGENT_PLAYBOOK.md`.

## Decision flow

1. **Whole MHI2/MHI2Q archive or supported raw filesystem image:** start with
   `tools/extract_firmware.py`.
2. **Interactive shell workflow on Linux/WSL/Git Bash:** use
   `tools/mhi2-extract.sh`, which wraps the supported extractor workflow.
3. **Unknown or intentionally opaque binary:** use `tools/binary_probe.py`.
4. **Existing SWDL metadata that must be audited/refreshed:** use
   `tools/metainfo2.py`, then `tools/update_txt.py` when `update.txt` also needs
   its integrity fields refreshed.
5. **MHI2 LSD JXE to JAR:** use `tools/jxe2jar/convert-jxe.ps1`.
6. **MH2P/Alpine `LZ4_` Stage-2 image:** use the bounded tools under
   `tools/experimental/` and read `docs/MH2P_GUIDE.md` first.

If a tool cannot prove the expected format or bounds, stop and preserve the input.
Do not weaken validation simply to make one firmware sample pass.

## Common safety contract

The toolkit is host-side. Inputs are treated as read-only. Extraction commands require
a new output directory and refuse to reuse an existing one. Symlinks and special
filesystem entries are represented as metadata instead of being created blindly on
the host. Parser bounds, path validation, source hashes, collision checks and
fresh-output rules are part of the correctness model.

Generated firmware trees, JXE/JAR conversions, proprietary binaries and device-specific
data stay outside Git.

## tools/extract_firmware.py

**Purpose:** primary supported extractor/orchestrator for MHI2/MHI2Q archive and raw-image
workflows.

**Typical inputs:** stock `.7z`/`.zip` firmware package, QNX6 `.img`/`.bin`, QNX
IFS `.ifs`, or QNX EFS `.efs`.

**Typical outputs:** verified raw selected members, filesystem trees, metadata, SHA-256
records and `extraction_manifest.json`. A failed extraction keeps the partial output
and records a freeze ledger instead of cleaning it up.

**Dependencies:** Python 3.10+, 7-Zip for archives, and external qnxmount/dumpifs/LZO
support only for the paths that require them. See `DEPENDENCIES.md`.

**Plan before writing:**

```powershell
python .\tools\extract_firmware.py --source .\firmware\update.7z --plan
```

**Extract selected MHI2 components:**

```powershell
python .\tools\extract_firmware.py `
  --source .\firmware\update.7z `
  --output .\exports\mhi2-r1 `
  --component rcc --component mmx
```

Use `--expected-sha256` when you have an authoritative source hash. Use
`--variant auto|50|70|both` only when the selected archive layout supports it.

## tools/mhi2-extract.sh

**Purpose:** shell/menu wrapper around the extraction workflow.

**Use when:** working under Linux, WSL or Git Bash and you want an interactive entry
point or a concise non-interactive wrapper.

```bash
bash tools/mhi2-extract.sh
bash tools/mhi2-extract.sh --source ./firmware/update.7z --output ./exports/mhi2-r1 --component mmx
```

The wrapper does not relax extractor validation.

## tools/binary_probe.py

**Purpose:** bounded inspection of an unrecognized or deliberately opaque binary without
executing or modifying it.

**Output:** JSON containing SHA-256, byte length, entropy, bounded printable strings and
known marker offsets.

```powershell
python tools/binary_probe.py path\to\payload.img --output payload.analysis.json
```

Use this before inventing a parser for a payload whose container/filesystem type has not
been established.

## tools/metainfo2.py

**Purpose:** audit and conservatively refresh supported `metainfo2.txt` integrity and
size fields.

**Default behavior:** audit/report only. In-place writes require `--write`.

```powershell
python tools/metainfo2.py path\to\metainfo2.txt --root path\to\package
python tools/metainfo2.py path\to\metainfo2.txt --root path\to\package --write
```

The helper preserves the historical signed-prefix/editable-tail boundary where detected,
handles supported file/application/bootloader/directory sections and refuses to invent
unsupported transaction structure.

## tools/update_txt.py

**Purpose:** refresh the integrity fields of an existing Harman `update.txt` after the
associated `metainfo2.txt` has been audited or changed.

```powershell
python tools/update_txt.py path\to\update.txt `
  --metainfo path\to\metainfo2.txt `
  --output refreshed-update.txt
```

The command requires the expected existing fields; it does not create a new SWDL
transaction format.

## tools/jxe2jar/convert-jxe.ps1

**Purpose:** reproducible JXE-to-JAR conversion using the externally fetched, pinned
`luka-dev/jxe2jar` revision.

```powershell
.\tools\jxe2jar\convert-jxe.ps1 `
  -InputJxe 'C:\path\to\lsd.jxe' `
  -OutputDirectory 'C:\path\to\new-output'
```

The wrapper verifies the exact upstream commit, rejects a dirty checkout, validates the
resulting ZIP/JAR and writes `conversion-manifest.json` with source/output hashes.
Upstream source is not vendored here. See `tools/jxe2jar/README.md`.

## tools/experimental/extract_mh2p_stage2_imagefs.py

**Purpose:** validate and decode one bounded raw LZ4 block from the observed MH2P/Alpine
`LZ4_` Stage-2 layout and materialize a leading ImageFS only when the declared image
fits completely.

**Use when:** you have an extracted MH2P `main_stage2.img` and want the smallest,
most conservative proof.

**Dependency for real decompression:** external Python `lz4` package.

```powershell
python tools/experimental/extract_mh2p_stage2_imagefs.py `
  --source path\to\main_stage2.img `
  --output path\to\new-mh2p-imagefs-output `
  --expected-sha256 <sha256>
```

Use `--lz4-module-root` only when the `lz4` package lives in a separate Python
site-packages directory.

This is not a general MH2P container decoder.

## tools/experimental/extract_mh2p_stage2_segment_prefix.py

**Purpose:** follow the observed Stage-2 size-table prefix, validate each complete raw
LZ4 block, check 512-byte padding/alignment and scan the decoded prefix for complete or
directory-valid incomplete ImageFS images.

Only file extents fully present inside a validated prefix are materialized.

```powershell
python tools/experimental/extract_mh2p_stage2_segment_prefix.py `
  --source path\to\main_stage2.img `
  --output path\to\new-mh2p-segment-output `
  --expected-sha256 <sha256>
```

Use this when the one-block probe is insufficient, but do not interpret a successful run
as proof that the remaining Stage-2 container or another MH2P train uses identical
semantics. See `MH2P_GUIDE.md`.

## Library modules

Files such as `android_image.py`, `filesystem_readers.py`, `imagefs.py`,
`mifs_stage2.py`, `qnx_ifs.py` and `ucl_nrv2b.py` are parser/library building
blocks used by the higher-level commands. They are not the preferred first entry point
for routine extraction unless you are developing or testing a parser.

## For AI agents

Before acting:

- identify the exact firmware family/train and input type;
- choose the narrowest tool that already supports that format;
- run a plan/audit mode first when available;
- preserve exact source hashes in reports;
- distinguish measured evidence from inference;
- never claim family-wide compatibility from one firmware;
- keep proprietary or device-specific outputs outside Git;
- run `python -m compileall -q tools tests` and
  `python -m unittest discover -s tests -v` after code changes.

If the requested operation falls outside this guide, inspect the parser and tests before
creating a new workflow rather than guessing from filenames.
