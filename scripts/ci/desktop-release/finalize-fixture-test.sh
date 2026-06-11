#!/usr/bin/env bash
# Regression fixtures for finalize-release.sh platform/signature matching (no gh/network).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=pick-platform-asset.sh
source "${SCRIPT_DIR}/pick-platform-asset.sh"

read_asset_signature() {
  local asset_name="$1"
  local sig_path="${FIXTURE_ASSETS}/${asset_name}.sig"
  [[ -f "$sig_path" ]] || return 1
  local raw
  raw="$(<"$sig_path")"
  printf '%s' "${raw%$'\n'}"
}

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT
FIXTURE_ASSETS="${WORK_DIR}/assets"
mkdir -p "$FIXTURE_ASSETS"

echo "placeholder" >"$FIXTURE_ASSETS/MyrmAgent.app.tar.gz"
echo "sig-aarch64" >"$FIXTURE_ASSETS/MyrmAgent.app.tar.gz.sig"
echo "placeholder" >"$FIXTURE_ASSETS/MyrmAgent_x64.app.tar.gz"
echo "sig-x64" >"$FIXTURE_ASSETS/MyrmAgent_x64.app.tar.gz.sig"
echo "placeholder" >"$FIXTURE_ASSETS/MyrmAgent_x64.nsis.zip"
echo "sig-win" >"$FIXTURE_ASSETS/MyrmAgent_x64.nsis.zip.sig"
echo "placeholder" >"$FIXTURE_ASSETS/setup.exe"
echo "placeholder" >"$FIXTURE_ASSETS/MyrmAgent_0.1.33_amd64.AppImage.tar.gz"
echo "sig-linux" >"$FIXTURE_ASSETS/MyrmAgent_0.1.33_amd64.AppImage.tar.gz.sig"

aarch64_asset="$(pick_platform_asset darwin-aarch64 "$FIXTURE_ASSETS")"
[[ "$aarch64_asset" == "MyrmAgent.app.tar.gz" ]] || {
  echo "expected MyrmAgent.app.tar.gz, got ${aarch64_asset}" >&2
  exit 1
}

x64_asset="$(pick_platform_asset darwin-x86_64 "$FIXTURE_ASSETS")"
[[ "$x64_asset" == "MyrmAgent_x64.app.tar.gz" ]] || {
  echo "expected MyrmAgent_x64.app.tar.gz, got ${x64_asset}" >&2
  exit 1
}

sig="$(read_asset_signature "$aarch64_asset")"
[[ "$sig" == "sig-aarch64" ]] || {
  echo "unexpected aarch64 signature: ${sig}" >&2
  exit 1
}

win_asset="$(pick_platform_asset windows-x86_64 "$FIXTURE_ASSETS")"
[[ "$win_asset" == "MyrmAgent_x64.nsis.zip" ]] || {
  echo "expected MyrmAgent_x64.nsis.zip, got ${win_asset}" >&2
  exit 1
}
win_sig="$(read_asset_signature "$win_asset")"
[[ "$win_sig" == "sig-win" ]] || {
  echo "unexpected windows signature: ${win_sig}" >&2
  exit 1
}

linux_asset="$(pick_platform_asset linux-x86_64 "$FIXTURE_ASSETS")"
[[ "$linux_asset" == "MyrmAgent_0.1.33_amd64.AppImage.tar.gz" ]] || {
  echo "expected MyrmAgent_0.1.33_amd64.AppImage.tar.gz, got ${linux_asset}" >&2
  exit 1
}
linux_sig="$(read_asset_signature "$linux_asset")"
[[ "$linux_sig" == "sig-linux" ]] || {
  echo "unexpected linux signature: ${linux_sig}" >&2
  exit 1
}

echo "[finalize-fixture-test] OK"
