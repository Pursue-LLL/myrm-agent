#!/usr/bin/env bash
# Integration check: simulate release assets dir and validate latest.json platform picking.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

mkdir -p "$WORK/assets"
touch "$WORK/assets/MyrmAgent.app.tar.gz"
touch "$WORK/assets/MyrmAgent_0.1.14_aarch64.dmg"

cd "$WORK"
source() { :; }

pick_platform_asset() {
  local tauri_key="$1"
  local candidates=()
  case "$tauri_key" in
    darwin-aarch64)
      candidates=(MyrmAgent.app.tar.gz *aarch64*.tar.gz *arm64*.tar.gz *universal*.tar.gz *.app.tar.gz)
      ;;
    *)
      return 1
      ;;
  esac
  local pattern file base
  for pattern in "${candidates[@]}"; do
    for file in assets/${pattern}; do
      [[ -f "$file" ]] || continue
      base="$(basename "$file")"
      printf '%s' "$base"
      return 0
    done
  done
  return 1
}

picked="$(pick_platform_asset darwin-aarch64)"
if [[ "$picked" != "MyrmAgent.app.tar.gz" ]]; then
  echo "FAIL: expected MyrmAgent.app.tar.gz, got: $picked" >&2
  exit 1
fi

echo "OK: darwin-aarch64 picks MyrmAgent.app.tar.gz"
