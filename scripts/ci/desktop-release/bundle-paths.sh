#!/usr/bin/env bash
# Portable helpers for locating Tauri bundle outputs (source this file; do not execute).

is_release_bundle_path() {
  case "$1" in
    *release/bundle/* | *release\\bundle\\*) return 0 ;;
    *) return 1 ;;
  esac
}

is_updater_bundle_path() {
  local path="$1"
  is_release_bundle_path "$path" || return 1
  case "$path" in
    *.AppImage.tar.gz | *.nsis.zip | *.msi.zip) return 0 ;;
    */macos/*.tar.gz | *\\macos\\*.tar.gz) return 0 ;;
    *) return 1 ;;
  esac
}
