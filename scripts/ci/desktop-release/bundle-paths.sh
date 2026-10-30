#!/usr/bin/env bash
# Portable helpers for locating Tauri bundle outputs (source this file; do not execute).

_normalize_bundle_path() {
  printf '%s' "${1//\\//}"
}

# Tauri writes every output directly into release/bundle/<kind>/ (dmg, macos, nsis, msi, appimage, deb).
# Anything deeper is a bundle's own content: a .app or .AppDir carries the whole resource tree, and that
# tree holds archives and executables of its own which must never be signed or published.
is_release_bundle_path() {
  local path
  path="$(_normalize_bundle_path "$1")"
  [[ "$path" =~ release/bundle/[^/]+/[^/]+$ ]]
}

is_updater_bundle_path() {
  local path
  path="$(_normalize_bundle_path "$1")"
  is_release_bundle_path "$path" || return 1
  case "$path" in
    *.AppImage.tar.gz | *.nsis.zip | *.msi.zip) return 0 ;;
    */macos/*.tar.gz) return 0 ;;
    */nsis/*-setup.exe) return 0 ;;
    *) return 1 ;;
  esac
}
