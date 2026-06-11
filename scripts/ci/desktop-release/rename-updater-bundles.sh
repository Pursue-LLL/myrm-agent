#!/usr/bin/env bash
# Give platform-specific updater bundles stable names before gh release upload.
set -euo pipefail

PLATFORM="${1:?Usage: rename-updater-bundles.sh <macos-intel|windows>}"
ROOT="${2:-myrm-agent-desktop/src-tauri/target}"

shopt -s nullglob

rename_pair() {
  local src="$1"
  local dst="$2"
  [[ -f "$src" ]] || return 0
  if [[ "$src" == "$dst" ]]; then
    return 0
  fi
  if [[ -f "$dst" ]]; then
    echo "[rename-updater-bundles] ERROR: destination already exists: $(basename "$dst")" >&2
    exit 1
  fi
  mv "$src" "$dst"
  if [[ -f "${src}.sig" ]]; then
    mv "${src}.sig" "${dst}.sig"
  fi
  echo "[rename-updater-bundles] $(basename "$src") -> $(basename "$dst")"
}

case "$PLATFORM" in
  macos-intel)
    for dir in "$ROOT"/*/release/bundle/macos "$ROOT/release/bundle/macos"; do
      [[ -d "$dir" ]] || continue
      rename_pair "$dir/MyrmAgent.app.tar.gz" "$dir/MyrmAgent_x64.app.tar.gz"
    done
    ;;
  windows)
    for dir in "$ROOT"/*/release/bundle/nsis "$ROOT/release/bundle/nsis"; do
      [[ -d "$dir" ]] || continue
      for src in "$dir"/*-setup.nsis.zip; do
        [[ -f "$src" ]] || continue
        rename_pair "$src" "$dir/MyrmAgent_x64.nsis.zip"
      done
    done
    ;;
  *)
    echo "[rename-updater-bundles] unknown platform: ${PLATFORM}" >&2
    exit 1
    ;;
esac
