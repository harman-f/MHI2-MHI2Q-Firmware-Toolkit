# Agent playbook

This file translates common analyst requests into concrete repository workflows. It is
written for AI agents, but the same recipes are useful to human users.

Read `FIRMWARE_IMAGE_PRIMER.md` first when the artifact type is unclear. Read
`TOOL_GUIDE.md` for the exact tool contract.

## If the user says: "Unpack this firmware"

1. Identify the exact source archive and calculate/record SHA-256.
2. Run a plan first:
   `python tools/extract_firmware.py --source <archive> --plan`.
3. Inspect the reported package prefix, variants and components.
4. Choose the smallest useful component set instead of extracting everything by default.
5. Use a new output directory and, when possible, pass `--expected-sha256`.
6. Review `extraction_manifest.json` and any `PARTIAL`/freeze records before calling the
   extraction complete.

Useful shortcuts:

- RCC only: `--component rcc`
- MMX/application side: `--component mmx`
- MIFS Stage-2 / LSD source: `--component java`
- explicit hardware variant: `--variant 50` or `--variant 70`

## If the user says: "I only need LSD / Java"

Use the narrow Java path instead of a full export:

```powershell
python tools/extract_firmware.py `
  --source firmware.7z `
  --output export-java `
  --component java
```

Then, if an `lsd.jxe` was exported, convert it with
`tools/jxe2jar/convert-jxe.ps1`. Keep the original JXE hash and the generated
`conversion-manifest.json` together.

If the goal is comparison between firmware versions, compare exact JXE/JAR hashes and
class/file inventories before interpreting source-level differences.

## If the user says: "Compare two firmware versions"

Prefer a normalized comparison:

1. extract the same component scope from both sources;
2. preserve both source hashes and manifests;
3. compare normalized filesystem paths, sizes and SHA-256 values;
4. separate identical, changed, added and removed files;
5. only decompile/inspect the changed Java/native subset;
6. report train/OEM/MU differences so platform changes are not mistaken for version changes.

Do not compare only archive byte size or compressed member size.

## If the user says: "What is this .img/.bin/.ifs file?"

Do not guess from the suffix.

1. hash it;
2. run `tools/binary_probe.py`;
3. inspect validated magic/headers and the theory in `FIRMWARE_IMAGE_PRIMER.md`;
4. if a known parser matches, use that parser;
5. otherwise keep the artifact opaque and document the candidate hypotheses.

A printable string such as `ANDROID!` or `imagefs` is evidence, not proof of the
complete surrounding format.

## If the user says: "Find where a component lives"

Distinguish three questions:

- Where is it in the update archive?
- Where is it inside the decoded filesystem?
- Where is it located in physical flash/runtime memory?

Use package manifests for the first, filesystem metadata for the second, and
`MHI2_FLASH_LAYOUT_AND_RECOVERY.md` plus unit-specific evidence for the third.
Never translate one offset class into another without evidence.

## If the user says: "Extract an RCC_fs0/full flash dump"

The current public toolkit does not claim a universal full-dump carver. Do not apply one
historical Stage-2 offset as a constant.

Use the MHI2 image/flash documentation to identify candidate QNX signatures and validated
lengths. Report ambiguity if multiple plausible images exist. A future generic dump mode
should enumerate candidates rather than silently choose one.

## If the user says: "Rebuild or modify a firmware package"

Separate package metadata reconstruction from filesystem-image rebuilding.

For an existing unpacked package tree:

1. preserve an immutable original;
2. make the intended payload change in a working copy;
3. run `tools/metainfo2.py ... --root ...` in audit mode;
4. review all planned size/hash/sidecar changes;
5. only then use `--write`;
6. audit again;
7. refresh an existing `update.txt` with `tools/update_txt.py` if required.

Do not imply that this rebuilds QNX6/IFS/EFS images. Consult
`REPACK_AND_METAINFO.md` for the current capability boundary.

## If the user says: "Analyze Quickboot / an unknown boot payload"

Start read-only:

1. preserve exact bytes and SHA-256;
2. run `binary_probe.py`;
3. record marker offsets and entropy;
4. if no validated container/filesystem exists, keep the status `PARTIAL`;
5. use an external native-analysis tool such as Ghidra only after documenting the input
   hash and analysis settings.

Do not infer execution semantics from names or strings alone.

## If the user says: "Analyze MH2P"

First identify whether the task is normal app/EFS content or the `LZ4_` Stage-2 path.

For Stage-2:

1. read `MH2P_GUIDE.md`;
2. hash the exact `main_stage2.img`;
3. start with `extract_mh2p_stage2_imagefs.py` for a bounded first proof;
4. move to `extract_mh2p_stage2_segment_prefix.py` only when the observed header/block
   model matches;
5. stop at the first unproven source boundary;
6. record the exact train as a new validation sample.

Current public evidence is one strong VW G36 P2838 baseline, not universal MH2P support.

## If the user says: "Can this work on another train/OEM?"

Answer from evidence, not naming similarity.

Check:

- exact platform family and train;
- package path/layout;
- wrapper magic and header invariants;
- variant selection;
- filesystem type;
- whether the parser has been exercised on an independent sample.

If only one sample supports the hypothesis, say so and propose a read-only validation run
before changing parser rules.

## If the user says: "What else can I do with this toolkit?"

Point out the less-obvious capabilities when relevant:

- plan an extraction without writing output;
- select only RCC, MMX or Java scope;
- pin the source SHA-256;
- inspect opaque binaries without executing them;
- preserve unknown payloads while still extracting known filesystems;
- reconstruct supported `metainfo2.txt` / `update.txt` integrity fields;
- convert LSD JXE reproducibly with a pinned external converter;
- validate MH2P Stage-2 prefixes without pretending the whole family is solved;
- use manifests and hashes as a normalized basis for firmware-to-firmware comparisons.

## Agent completion checklist

Before reporting a task complete:

- identify the exact input and family/train;
- state what was parsed versus retained raw;
- include hashes or manifest references where practical;
- distinguish complete, partial and opaque results;
- keep proprietary/device-specific outputs outside Git;
- do not weaken bounds/checks to obtain a successful result;
- update documentation when a newly validated firmware changes the support matrix;
- after code changes, run compileall and the unit-test suite.
