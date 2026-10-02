# Legacy toolkit retirement audit — 2026-10-02

## Decision

The legacy repository `harman-f/MHI2-MHI2Q-Firmware-Toolkit_old` is no longer required as an
operational source once the active migration/follow-up pull requests are merged.

Active authority:

```text
harman-f/MHI2-MHI2Q-MH2P-Firmware-Toolkit
branch: main
```

Legacy source HEAD audited:

```text
3291740d11c2a8367026bb246b3ce4bbc094577e
```

## Tree comparison

The legacy `main` tree contained 42 files. The active repository contains the migrated/superseding
toolkit plus new CI, agent documentation, JXE-wrapper and MH2P/Alpine material.

The only legacy-current-tree paths intentionally not migrated are:

```text
data/mhi2_firmware_access_v4.0.csv
data/mhi2_root_hash_passwords_v4.0.csv
docs/FACTORY_ACCESS_REFERENCE.md
tests/test_firmware_access.py
tools/firmware_access.py
```

These credential-oriented reference paths are deliberate exclusions and are not required by the
firmware extraction/analysis toolkit. They must not be re-imported merely for tree parity.

The legacy repository has one branch (`main`), no tags, no releases, and no standalone issues.
It has four merged pull requests.

## Legacy pull-request review salvage

The merged legacy PR discussions were checked before retirement so useful review findings would not
exist only in a repository scheduled for deletion.

### PR 1 — hardening/repack analysis

Review findings:

- constrain `Dir` processing to the package root;
- make opaque-report filenames unique per member path;
- bound captured printable-string length.

All three behaviors are represented in the active code/tests. No additional salvage action is
required.

### PR 2 — metainfo expansion/reference data

Review findings included:

- keep `Dir` sidecars inside the package root — already represented in the active
  `safe_section_directory()` validation;
- serialize nested files with relative paths — carried forward in the retirement follow-up;
- build parent `hashes.txt` from planned child-sidecar bytes, not stale on-disk child metadata —
  carried forward in the retirement follow-up;
- insert a line separator before new checksum rows when the anchor is an unterminated final line —
  carried forward in the retirement follow-up.

Synthetic regressions accompany the carried-forward parser fixes.

### PR 3 — review-follow-up hardening

This PR contained the first follow-up fixes. Automated review did not add technical findings because
the review quota was exhausted at that time.

### PR 4 — public-release documentation

The review correctly identified that a statement claiming one author/committer identity for the
publication history was too strong. The active `PROVENANCE.md` is corrected in the retirement
follow-up to describe mixed maintainer/automation/tooling identities and to rely on repository
history, reviewed changes and hashes instead.

## History boundary

Deleting the legacy repository will remove its original Git commit graph and PR discussion UI.
That history is intentionally **not** imported wholesale into the public successor because the
legacy history contains the deliberately excluded credential-oriented paths above.

Historical commit SHAs may remain in dated research reports as provenance labels. They are not
expected to resolve in the active repository after retirement and must not be treated as current
Git refs.

The active source tree, tests, migration audit, this retirement audit, and the Research repository's
toolkit-authority note are the retained operational record.
