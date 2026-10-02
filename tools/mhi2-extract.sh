#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-3.0-only
set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
python_bin="${MHI2_PYTHON:-python3}"

# Noninteractive use passes all arguments directly to the Python CLI.
if (( $# > 0 )); then
  exec "$python_bin" "$script_dir/extract_firmware.py" "$@"
fi

read -r -p 'Firmware archive/image path: ' source_path
read -r -p 'New export directory (must not exist): ' output_path
printf '\nExport selection:\n'
printf '  1) Everything (RCC + MMX)\n'
printf '  2) RCC only\n'
printf '  3) MMX only\n'
printf '  4) Java only (MIFS Stage 2 + separate lsd.jxe export)\n'
read -r -p 'Choose [1-4]: ' selection

case "$selection" in
  1) components=(--component rcc --component mmx) ;;
  2) components=(--component rcc) ;;
  3) components=(--component mmx) ;;
  4) components=(--component java) ;;
  *) printf 'Invalid selection: %s\n' "$selection" >&2; exit 2 ;;
esac

if [[ "$selection" == 1 || "$selection" == 3 ]]; then
  read -r -p 'Also export a separate Java source copy? [y/N]: ' java_copy
  case "${java_copy,,}" in
    y|yes) components+=(--component java) ;;
    '') ;;
    n|no) ;;
    *) printf 'Invalid answer: %s\n' "$java_copy" >&2; exit 2 ;;
  esac
fi


exec "$python_bin" "$script_dir/extract_firmware.py" \
  --source "$source_path" --output "$output_path" "${components[@]}"
