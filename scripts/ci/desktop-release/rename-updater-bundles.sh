#!/usr/bin/env bash
# Give platform-specific updater bundles stable names before gh release upload.
set -euo pipefail

PLATFORM="${1:?Usage: rename-updater-bundles.sh <macos-intel|windows>}"
ROOT="${2:-myrm-agent-desktop/src-tauri/target}"
# GHA Windows: GITHUB_WORKSPACE is D:\...\repo with mixed separators; globs need forward slashes.
ROOT="${ROOT//\\//}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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

renamed=0

case "$PLATFORM" in
  macos-intel)
    for dir in "$ROOT"/*/release/bundle/macos "$ROOT/release/bundle/macos"; do
      [[ -d "$dir" ]] || continue
      if [[ -f "$dir/MyrmAgent.app.tar.gz" ]]; then
        rename_pair "$dir/MyrmAgent.app.tar.gz" "$dir/MyrmAgent_x64.app.tar.gz"
        renamed=1
      fi
    done
    ;;
  windows)
    for src in \
      "$ROOT"/release/bundle/nsis/*-setup.nsis.zip \
      "$ROOT"/*/release/bundle/nsis/*-setup.nsis.zip; do
      [[ -f "$src" ]] || continue
      rename_pair "$src" "$(dirname "$src")/MyrmAgent_x64.nsis.zip"
      renamed=1
    done
    if [[ "$renamed" -eq 0 ]]; then
      while IFS= read -r src; do
        [[ -n "$src" ]] || continue
        rename_pair "$src" "$(dirname "$src")/MyrmAgent_x64.nsis.zip"
        renamed=1
      done < <(bash "${SCRIPT_DIR}/bundle-find.sh" "$ROOT" -type f -name '*-setup.nsis.zip' 2>/dev/null || true)
    fi
    ;;
  *)
    echo "[rename-updater-bundles] unknown platform: ${PLATFORM}" >&2
    exit 1
    ;;
esac

if [[ "$renamed" -eq 0 ]]; then
  echo "[rename-updater-bundles] ERROR: no ${PLATFORM} updater bundle renamed under ${ROOT}" >&2
  ls -la "$ROOT/release/bundle/nsis" 2>/dev/null >&2 || true
  ls -la "$ROOT"/*/release/bundle/nsis 2>/dev/null >&2 || true
  exit 1
fi
