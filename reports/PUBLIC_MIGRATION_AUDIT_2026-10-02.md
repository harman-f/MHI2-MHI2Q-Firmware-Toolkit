# Public toolkit migration and refresh audit — 2026-10-02

## Scope

This audit records the migration from the archived source repository
`harman-f/MHI2-MHI2Q-Firmware-Toolkit_old` into the active standalone public
repository `harman-f/MHI2-MHI2Q-MH2P-Firmware-Toolkit`.

The target repository was initially created under the temporary name
`harman-f/MHI2-MHI2Q-Firmware-Toolkit` during the migration and was renamed on
2026-10-02 after MH2P/Alpine documentation and tooling were incorporated. The
final name above is the only operational repository authority.

Source baseline:

- archived repository branch: `main`
- source HEAD: `3291740d11c2a8367026bb246b3ce4bbc094577e`

The active repository is intentionally independent: no private research
repository names, private workstation paths, or private cache paths are valid
runtime/documentation dependencies.

## Migrated stable capability

The public core retains the host-side MHI2/MHI2Q functionality from the
archived baseline:

- archive selection and safe extraction orchestration;
- QNX6 MMX application filesystem inventory/materialization;
- RCC IFS extraction through external `dumpifs`;
- QNX EFS extraction;
- MIFS Stage-2 LZOZ handling;
- Android-style Stage-1/EIFS module parsing;
- Emergency IFS/ImageFS handling;
- bounded opaque-binary inspection;
- metainfo2/update.txt audit/reconstruction helpers;
- synthetic/unit tests and dated validation reports.

Firmware images and generated filesystem trees remain outside Git.

## New public additions

### LSD/JXE

The preferred external JXE converter was rechecked on 2026-10-02.

- upstream: `luka-dev/jxe2jar`
- current reviewed pin: `9eeb45bbf14bf8afe3452c7be96a4d1f0206a286`
- previous documented pin: `3bae6e82177c7084a008c42373042e6eebf5653e`
- upstream delta: 24 commits

The newer revision includes substantial converter/decompiler-recovery work,
including constant-pool hardening, Modified UTF-8 fixes, InnerClasses and
EnclosingMethod reconstruction, float recovery, un-inlining and compile-check
tooling.

No clear top-level redistribution license was found at the reviewed pin.
Therefore upstream code is not vendored. The project-authored
`tools/jxe2jar/convert-jxe.ps1` wrapper fetches the exact pin, verifies the
checkout, performs JXE-to-JAR conversion, validates the output JAR and records
input/output hashes plus the converter commit.

### Experimental MH2P/Alpine work

Bounded `LZ4_` Stage-2 probes are published under `tools/experimental/`.
They validate only proven prefixes/segments and are deliberately not described
as a complete MH2P container decoder. The shared ImageFS reader now supports a
strict incomplete-prefix mode that materializes only fully present file
extents.

## External tool references checked

Reviewed on 2026-10-02:

- `NetherlandsForensicInstitute/qnxmount`: `0379c064975d5bbe3595ac7e3d149ea789406794`
- `lclevy/dumpifs`: `bb77c71bae3ebb54b8b7469ac810c890530f3213`
- `JeniCzech92/lsdtool`: `4bf44aac95f03cf3b81985dd9ccd9c81fb1ef63d`
- `luka-dev/qnx65-armv7-toolchain`: `baa45224f18ae6b13c2e9c77c6663bb8181eb6a1`
- Ghidra latest stable release: 12.1.4, archive SHA-256
  `ddac49f903da9d5bac833e5cc79395098b9c33cfd3279be5f31bd00387d2d4db`

## GitHub / CI refresh

CI was refreshed to current reviewed GitHub Action revisions:

- `actions/checkout` v7.0.1:
  `3d3c42e5aac5ba805825da76410c181273ba90b1`
- `actions/setup-python` v7.0.0:
  `5fda3b95a4ea91299a34e894583c3862153e4b97`
- `github/codeql-action` v4:
  `2892aa5e19bbd11bc0cff5427e3b750a04d9e3c2`

The test workflow runs on Python 3.10 and 3.12. A public-hygiene test rejects
known private-project/path markers and firmware/generated binary artifacts.
CodeQL and Dependabot configuration are included.

## Agent rules

A root `AGENTS.md` now makes the public-repository boundary explicit for
future agents: standalone imports, no private paths/repositories, no generated
firmware artifacts, exact external pins, tests for parser changes, and clear
stable/experimental capability labels.

## Deliberate exclusions

Credential-oriented factory-access tables and their lookup helper were not
copied into the active migration. They are not required for firmware
extraction, filesystem parsing, LSD/JXE conversion, metadata analysis or the
experimental MH2P probes.

## Validation

The migration PR runs:

- `python -m compileall -q tools tests`;
- `python -m unittest discover -s tests -v` on Python 3.10 and 3.12;
- repository-publication hygiene checks;
- CodeQL for Python.

At the time of this audit, both Python matrix jobs pass with 69 tests each.
