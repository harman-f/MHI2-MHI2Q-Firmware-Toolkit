# Pinned JXE to JAR workflow

This directory contains a small project-authored wrapper for the external
[luka-dev/jxe2jar](https://github.com/luka-dev/jxe2jar) converter. Upstream
source is **not vendored** here.

Reviewed upstream state on 2026-10-02:

- repository: `luka-dev/jxe2jar`
- pinned commit: `9eeb45bbf14bf8afe3452c7be96a4d1f0206a286`
- previous toolkit reference: `3bae6e82177c7084a008c42373042e6eebf5653e`
- delta from the previous pin: 24 commits
- licensing boundary: no clear top-level license grant was found at the
  reviewed pin, so this toolkit does not copy or redistribute upstream code.

The current upstream revision contains substantial improvements beyond the old
pin, including J9/JVM conversion fixes, `InnerClasses` and
`EnclosingMethod` reconstruction, Modified UTF-8 fixes, float recovery,
constant-pool hardening, constant un-inlining tooling, and compile/decompiler
repair tooling. For advanced decompilation/recovery workflows consult the
pinned upstream repository directly.

## Usage

PowerShell 7:

```powershell
.\tools\jxe2jar\convert-jxe.ps1 `
  -InputJxe 'C:\path\to\lsd.jxe' `
  -OutputDirectory 'C:\path\to\new-output'
```

The wrapper:

1. creates/reuses a cache below
   `%LOCALAPPDATA%\MHI2FirmwareToolkit\tool-cache`;
2. fetches the exact pinned commit;
3. checks out that commit detached and rejects a dirty worktree;
4. executes only `src/jxe2jar.py`;
5. verifies the resulting ZIP/JAR and class count; and
6. writes `conversion-manifest.json` with source/output hashes and the exact
   converter commit.

The output directory must not already exist. Firmware/JXE inputs and generated
outputs remain local and must not be committed.

## Scope

This wrapper covers reproducible **JXE to JAR conversion**. It deliberately
does not vendor or silently execute the larger upstream decompilation,
constant-un-inlining, VM/JDK, or bundled-binary toolchains. Those are useful
for research, but each has its own provenance and redistribution boundary.
