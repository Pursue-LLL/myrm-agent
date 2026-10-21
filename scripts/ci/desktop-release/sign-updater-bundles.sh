#!/usr/bin/env bash
# Sign Tauri updater bundles when build did not emit .sig (macOS tar.gz, Windows setup.exe, AppImage, …).
set -euo pipefail

ROOT="${1:-myrm-agent-desktop/src-tauri/target}"
ROOT="${ROOT//\\//}"
DESKTOP_ROOT="${2:-myrm-agent-desktop}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=bundle-paths.sh
source "${SCRIPT_DIR}/bundle-paths.sh"

if [[ ! -d "$ROOT" ]]; then
  echo "[sign-updater-bundles] Target directory not found: ${ROOT}" >&2
  exit 1
fi

if [[ -z "${TAURI_SIGNING_PRIVATE_KEY:-}" ]]; then
  echo "[sign-updater-bundles] ERROR: TAURI_SIGNING_PRIVATE_KEY is unset." >&2
  exit 1
fi

bundles=()
while IFS= read -r line; do
  [[ -n "$line" ]] || continue
  is_updater_bundle_path "$line" || continue
  bundles+=("$line")
done < <(
  bash "${SCRIPT_DIR}/bundle-find.sh" "$ROOT" -type f | sort -u
)

if [[ ${#bundles[@]} -eq 0 ]]; then
  echo "[sign-updater-bundles] WARNING: No updater bundles under ${ROOT}" >&2
  find "$ROOT" -maxdepth 12 -type f 2>/dev/null | head -30 >&2 || true
  if [[ "${REQUIRE_UPDATER_BUNDLES:-}" == "1" ]]; then
    echo "[sign-updater-bundles] ERROR: REQUIRE_UPDATER_BUNDLES=1 but none found." >&2
    exit 1
  fi
  echo "[sign-updater-bundles] Skipping (installers may still publish; OTA omitted for this platform)."
  exit 0
fi

signed=0
for bundle in "${bundles[@]}"; do
  sig="${bundle}.sig"
  if [[ -f "$sig" ]]; then
    echo "[sign-updater-bundles] present: $(basename "$sig")"
    signed=$((signed + 1))
    continue
  fi
  echo "[sign-updater-bundles] signing: $(basename "$bundle")"
  bundle_rel="${bundle#${DESKTOP_ROOT}/}"
  (
    cd "$DESKTOP_ROOT"
    bun x @tauri-apps/cli signer sign "$bundle_rel"
  )
  if [[ ! -f "$sig" ]]; then
    echo "[sign-updater-bundles] ERROR: signer did not create ${sig}" >&2
    exit 1
  fi
  signed=$((signed + 1))
done

echo "[sign-updater-bundles] OK (${signed} updater signature file(s))"
