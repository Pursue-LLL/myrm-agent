#!/usr/bin/env bash
# Shared OTA asset picker for finalize-release.sh (source this file; do not execute).

pick_platform_asset() {
  local tauri_key="$1"
  local assets_dir="${2:-assets}"
  local candidates=()
  case "$tauri_key" in
    darwin-aarch64)
      # Apple Silicon is the only macOS target, so its bundle keeps Tauri's canonical name. Releases up to v0.1.39
      # also hold an Intel bundle (MyrmAgent_x64.app.tar.gz); no pattern below matches it and no key offers it.
      candidates=(MyrmAgent.app.tar.gz '*aarch64*.tar.gz' '*arm64*.tar.gz' '*universal*.tar.gz')
      ;;
    windows-x86_64)
      candidates=(
        MyrmAgent_x64-setup.exe
        '*x64-setup.exe'
        '*x86_64-setup.exe'
        '*x86_64*.msi.zip'
      )
      ;;
    linux-x86_64)
      candidates=('*x86_64*.AppImage.tar.gz' '*amd64*.AppImage.tar.gz' '*.AppImage.tar.gz')
      ;;
    *)
      return 1
      ;;
  esac
  local pattern file base
  shopt -s nullglob
  for pattern in "${candidates[@]}"; do
    for file in "${assets_dir}"/${pattern}; do
      [[ -f "$file" ]] || continue
      base="$(basename "$file")"
      printf '%s' "$base"
      return 0
    done
  done
  return 1
}
