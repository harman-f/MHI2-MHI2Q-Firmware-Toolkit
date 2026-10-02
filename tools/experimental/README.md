# Experimental tools

These tools are published because they capture useful, bounded format knowledge,
but they are **not** part of the stable MHI2/MHI2Q extraction contract.

## MH2P/Alpine Stage 2

- `extract_mh2p_stage2_imagefs.py` validates one bounded raw LZ4 block from the
  observed `LZ4_` layout, cross-checks it with python-lz4, and materializes a
  leading ImageFS only when the complete declared image fits.
- `extract_mh2p_stage2_segment_prefix.py` follows the observed sector-aligned
  size-table prefix, validates each complete LZ4 segment, and scans the decoded
  prefix for complete or directory-valid incomplete ImageFS images.

Both tools enforce fresh output directories and SHA-256 source pins when
provided. The segment-prefix tool materializes only file extents fully present
inside a validated prefix.

These probes do **not** claim to decode the complete MH2P `LZ4_` container.
Remaining bytes/table semantics may be unresolved. Generated trees may contain
device-specific key material and must remain local.

Actual decompression requires the external Python `lz4` package. The unit
tests exercise header, bounds, alignment and raw-LZ4 validation without firmware
samples.
