#!/usr/bin/env bash
# List Tauri bundle artifacts under src-tauri/target for gh release upload.
set -euo pipefail

ROOT="${1:-myrm-agent-desktop/src-tauri/target}"
ROOT="${ROOT//\\//}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=bundle-paths.sh
source "${SCRIPT_DIR}/bundle-paths.sh"

if [[ ! -d "$ROOT" ]]; then
  echo "[collect-bundle-assets] Target directory not found: ${ROOT}" >&2
  exit 1
fi

# Avoid find -path on Windows (backslash paths); filter with a shell case instead.
files=()
while IFS= read -r line; do
  [[ -n "$line" ]] || continue
  is_release_bundle_path "$line" || continue
  files+=("$line")
done < <(
  bash "${SCRIPT_DIR}/bundle-find.sh" "$ROOT" -type f \( \
    -name '*.dmg' -o -name '*.exe' -o -name '*.msi' \
    -o -name '*.nsis.zip' -o -name '*.msi.zip' \
    -o -name '*.AppImage' -o -name '*.AppImage.tar.gz' \
    -o -name '*.deb' -o -name '*.tar.gz' -o -name '*.sig' \
  \) | sort -u
)

if [[ ${#files[@]} -eq 0 ]]; then
  echo "[collect-bundle-assets] No bundle assets under ${ROOT}" >&2
  find "$ROOT" -maxdepth 8 -type f 2>/dev/null | head -50 >&2 || true
  exit 1
fi

printf '%s\n' "${files[@]}"
