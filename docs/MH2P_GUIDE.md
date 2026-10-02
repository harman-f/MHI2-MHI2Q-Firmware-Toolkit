# MH2P / Alpine guide

## Scope

MH2P/Alpine is a first-class documented family in this repository, but its current
validation breadth is intentionally narrower than MHI2.

The strongest current evidence is one Volkswagen G36 P2838 firmware baseline. That
sample was successfully exercised through archive inventory/extraction, QNX6 app
materialization, two EFS filesystems, LSD JAR handling and bounded Stage-2 recovery.
The result is technically strong for that exact sample. It is **not** evidence that all
MH2P/Alpine trains, OEM variants or software generations use identical layouts.

## Validation status

| Area | VW G36 P2838 result | Generalization |
|---|---|---|
| Firmware archive inventory | Successful | Sample-specific evidence |
| MMX2P app QNX6 filesystem | Successful | Likely reusable parser path; verify each train |
| EFS persist/system | Successful | Verify each train |
| App-side LSD JAR | Successfully identified and validated | Path/layout may vary |
| `LZ4_` Stage-2 | Strong bounded recovery evidence | Container semantics remain train-sensitive |
| ImageFS parsing | Successful on recovered Stage-2 images | Parser is reusable; surrounding container may differ |
| Quickboot / Stage1 semantics | Not fully decoded | No broad support claim |

The public tools deliberately preserve this distinction. A successful P2838 run should
be recorded as `MH2P/Alpine VW G36 P2838`, not simply as "MH2P supported".

The full P2838 validation included archive/app/EFS work that established the platform
layout. In this public toolkit, the explicitly MH2P-specific published commands are the
bounded Stage-2 probes under `tools/experimental/`; do not assume the stable MHI2 archive
orchestrator has identical MH2P routing unless that capability is present and tested.

## Published MH2P tools

The MH2P-specific public entry points currently live under `tools/experimental/`:

- `extract_mh2p_stage2_imagefs.py` — smallest bounded Stage-2 proof: validate one raw
  LZ4 block and materialize a leading complete ImageFS.
- `extract_mh2p_stage2_segment_prefix.py` — validate the observed size-table prefix,
  raw-LZ4 consumption, 512-byte alignment/padding and recover complete or safely bounded
  ImageFS content.

Both tools require a **new output directory**. Both can pin the source by SHA-256. Both
stop at an unproven boundary instead of reading beyond it.

## Recommended workflow

1. Record the exact firmware train/OEM/version and SHA-256 of the source archive.
2. Extract or otherwise obtain the exact `main_stage2.img` without modifying it.
3. Hash the Stage-2 input and keep the original read-only.
4. Start with the one-block ImageFS probe if the format is new or uncertain.
5. Use the segment-prefix probe only after the header and initial block behavior match the
   validated model.
6. Review the generated manifest before treating any materialized file as complete.
7. Keep decoded trees local. They can contain device-specific authentication/account data.
8. For a new train, describe the result as a new validation sample; do not silently promote
   experimental support to stable.

## What "worked" on the validated sample

For the VW G36 P2838 baseline, the extraction work demonstrated that the firmware contains
usable QNX filesystem structures and a recoverable segmented `LZ4_` Stage-2 stream. The
existing strict ImageFS reader was able to validate recovered filesystem images rather than
requiring relaxed bounds or checksum rules. That is why MH2P is included in this toolkit's
documented scope.

The important qualification is corpus size: this conclusion currently rests on one
firmware baseline for the full MH2P validation path. More trains should be tested before
moving MH2P from bounded/experimental to the same support class as the MHI2 core.

## When adding a second MH2P firmware

An agent or contributor should create a dated validation record containing:

- exact train/OEM/version and source SHA-256;
- archive member counts and relevant image hashes;
- which app/EFS/Stage-2 parsers were exercised;
- decoded segment and ImageFS counts;
- any path/layout differences from VW G36 P2838;
- failures without weakening parser safety checks;
- whether the result confirms, narrows or contradicts the existing layout hypothesis.

Only after multiple independent MH2P baselines exercise the same paths should documentation
promote a behavior from sample-specific evidence to family-level support.

## Relationship to MHI2/MHI2Q

MH2P shares useful filesystem and HMI concepts with MHI2-family work, but it is not silently
treated as the same platform. Reuse the generic QNX/ImageFS infrastructure where the bytes
prove compatibility; keep archive routing, Stage-2 container assumptions and platform
claims separate.
