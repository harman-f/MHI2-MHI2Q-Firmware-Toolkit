# Factory/root access reference data

This repository contains a normalized text extract of the historical public document **MIB2 HIGH - MHI2/Q Password List, V4.0, 16.06.2022**. The original 31-page PDF is not redistributed here.

The source document contains two useful views:

- a `HASH -> Password` reference sorted by root-password hash;
- known firmware/MU mappings grouped by OEM and region, including entries explicitly labelled `Emergency RCC`.

Its final page points readers to the long-standing public MIBSolution/M.I.B. resources and public M.I.B. wiki/discussion channels. The CSV files are intended as searchable interoperability/research reference data, not as a claim that every entry is current for every unit.

## Files

### data/mhi2_root_hash_passwords_v4.0.csv

Normalized transcription of the document's explicit **Sorted by HASH** section.

Columns:

- `hash`
- `password`
- `source_page`

Blank passwords are preserved as blank. Values are not guessed or completed from other sources.

Current extract: **112 rows**.

### data/mhi2_firmware_access_v4.0.csv

Normalized transcription of the known-firmware tables.

Columns:

- `mu_version` - normalized to four digits where the source MU is numeric;
- `brand` - source brand with Volkswagen normalized to `VW`;
- `region` - Europe/USA/China/Japan/Korea/Taiwan heading;
- `model` - model qualifier when present;
- `firmware` - firmware train/version string;
- `role` - `normal` or `emergency_rcc`;
- `role_evidence` - how the emergency classification was recovered from the source layout;
- `hash`;
- `password`;
- `source_page`;
- `source_raw` - retained normalized source line(s) for audit.

Current extract: **395 normalized rows** after removing one visually confirmed exact duplicate.

Some source rows intentionally or visibly omit a hash or password. Those fields remain blank. The lookup tool can separately show whether the global hash table contains a password for a row's hash; it does not overwrite the source value.

The PDF text layer is not perfectly faithful to the table layout. Two rows were therefore corrected after direct page-image review: the password on page 11 for `MHI2_ER_AUG24_P1061`, and the normal/Emergency ordering on page 14 for `MHI2Q_JP_AUG22_P1017`. One exact duplicate row for `MHIG_EU_AU_K1549` was removed from the normalized dataset. Source capitalization is otherwise preserved, including the document's inconsistent `Harman_f` / `harman_f` spelling.

## Lookup

Examples:

    python tools/firmware_access.py --firmware MHI2_ER_SKG13_P4526
    python tools/firmware_access.py --mu 1440 --brand Skoda
    python tools/firmware_access.py --hash 88PTlG6BPJk6M --hash-only
    python tools/firmware_access.py --brand Audi --region Europe --role emergency_rcc --json

Firmware matching is a case-insensitive substring match. Hash matching is exact.

The normal table output includes both the password transcribed on the firmware row and, separately, any password found for that hash in the document's global sorted-hash table. A mismatch is flagged rather than silently reconciled.

## Scope and limitations

These values are firmware-family reference data. They do not decrypt a QNX filesystem image by themselves, do not bypass SWDL integrity metadata, and do not perform network/device login. They are useful when a particular lab/unit/firmware workflow requires the corresponding historical factory/root credential.

The source is dated 2022. Treat it as historical evidence and verify an entry against the exact MU/train being examined.

The original PDF is not bundled. This repository makes no redistribution-license claim for that PDF; only the normalized factual reference extract above is included.
