#!/usr/bin/env bash
# Shared OTA asset picker for finalize-release.sh (source this file; do not execute).

pick_platform_asset() {
  local tauri_key="$1"
  local assets_dir="${2:-assets}"
  local candidates=()
  case "$tauri_key" in
    darwin-aarch64)
      # ARM keeps Tauri canonical name; Intel is renamed to MyrmAgent_x64.app.tar.gz before upload.
      candidates=(MyrmAgent.app.tar.gz '*aarch64*.tar.gz' '*arm64*.tar.gz' '*universal*.tar.gz')
      ;;
    darwin-x86_64)
      candidates=(MyrmAgent_x64.app.tar.gz '*x86_64*.tar.gz' '*x64*.tar.gz' '*intel*.tar.gz')
      ;;
    windows-x86_64)
      # Tauri v2 Windows OTA uses NSIS setup.exe (+ .sig); nsis.zip is ephemeral during bundling.
      candidates=(
        MyrmAgent_x64-setup.exe
        '*x64-setup.exe'
        '*x86_64-setup.exe'
        MyrmAgent_x64.nsis.zip
        '*x64*.nsis.zip'
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
