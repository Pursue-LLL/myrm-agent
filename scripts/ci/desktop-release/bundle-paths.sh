#!/usr/bin/env bash
# Portable helpers for locating Tauri bundle outputs (source this file; do not execute).

_normalize_bundle_path() {
  printf '%s' "${1//\\//}"
}

is_release_bundle_path() {
  local path="$(_normalize_bundle_path "$1")"
  case "$path" in
    *release/bundle/*) return 0 ;;
    *) return 1 ;;
  esac
}

is_updater_bundle_path() {
  local path="$(_normalize_bundle_path "$1")"
  is_release_bundle_path "$path" || return 1
  case "$path" in
    *.AppImage.tar.gz | *.nsis.zip | *.msi.zip) return 0 ;;
    */macos/*.tar.gz) return 0 ;;
    */nsis/*-setup.exe) return 0 ;;
    *) return 1 ;;
  esac
}
