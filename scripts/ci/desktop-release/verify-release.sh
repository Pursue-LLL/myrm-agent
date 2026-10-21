#!/usr/bin/env bash
# Post-finalize smoke: assert latest.json, OTA signatures, and installer checksum sidecars exist.
set -euo pipefail

TAG="${TAG:?Set TAG (e.g. v0.1.20)}"
REPO="${GITHUB_REPOSITORY:?Set GITHUB_REPOSITORY}"

MANIFEST_URL="https://github.com/${REPO}/releases/download/${TAG}/latest.json"
VERSION="${TAG#v}"

echo "[verify-release] Fetching ${MANIFEST_URL}"
manifest="$(curl -fsSL "$MANIFEST_URL")"

manifest_version="$(jq -r '.version // empty' <<<"$manifest")"
if [[ "$manifest_version" != "$VERSION" ]]; then
  echo "[verify-release] version mismatch: expected ${VERSION}, got ${manifest_version:-<empty>}" >&2
  exit 1
fi

platform_count="$(jq '.platforms | keys | length' <<<"$manifest")"
require_min="${REQUIRE_MIN_OTA_PLATFORMS:-1}"
if [[ "$platform_count" -lt "$require_min" ]]; then
  echo "[verify-release] latest.json has ${platform_count} OTA platform(s), require >= ${require_min}" >&2
  exit 1
fi

if [[ -n "${REQUIRED_OTA_PLATFORM_KEYS:-}" ]]; then
  missing_keys=0
  for key in ${REQUIRED_OTA_PLATFORM_KEYS}; do
    [[ -n "$key" ]] || continue
    if ! jq -e --arg k "$key" '.platforms[$k]' <<<"$manifest" >/dev/null; then
      echo "[verify-release] missing required OTA platform key: ${key}" >&2
      missing_keys=1
    fi
  done
  if [[ "$missing_keys" -ne 0 ]]; then
    exit 1
  fi
fi

missing_sig=0
while IFS= read -r key; do
  [[ -n "$key" ]] || continue
  if [[ -z "$(jq -r --arg k "$key" '.platforms[$k].signature // empty' <<<"$manifest")" ]]; then
    echo "[verify-release] missing OTA signature for platform: ${key}" >&2
    missing_sig=1
  fi
done < <(jq -r '.platforms | keys[]' <<<"$manifest")
if [[ "$missing_sig" -ne 0 ]]; then
  exit 1
fi

invalid_ota_url=0
while IFS= read -r key; do
  [[ -n "$key" ]] || continue
  url="$(jq -r --arg k "$key" '.platforms[$k].url // empty' <<<"$manifest")"
  case "$url" in
    *.tar.gz|*.nsis.zip|*.AppImage.tar.gz|*-setup.exe) ;;
    *)
      echo "[verify-release] invalid OTA artifact URL for ${key}: ${url}" >&2
      invalid_ota_url=1
      ;;
  esac
done < <(jq -r '.platforms | keys[]' <<<"$manifest")
if [[ "$invalid_ota_url" -ne 0 ]]; then
  exit 1
fi

release_json="$(gh release view "$TAG" --repo "$REPO" --json assets)"
asset_names="$(jq -r '.assets[].name' <<<"$release_json")"

require_asset() {
  local name="$1"
  if ! grep -Fxq "$name" <<<"$asset_names"; then
    echo "[verify-release] missing release asset: ${name}" >&2
    return 1
  fi
  return 0
}

ota_asset_missing=0
while IFS= read -r key; do
  [[ -n "$key" ]] || continue
  url="$(jq -r --arg k "$key" '.platforms[$k].url // empty' <<<"$manifest")"
  ota_file="${url##*/}"
  ota_file="${ota_file%%\?*}"
  if ! grep -Fxq "$ota_file" <<<"$asset_names"; then
    echo "[verify-release] OTA artifact missing on release: ${ota_file} (platform ${key})" >&2
    ota_asset_missing=1
  fi
  if ! grep -Fxq "${ota_file}.sig" <<<"$asset_names"; then
    echo "[verify-release] OTA signature missing on release: ${ota_file}.sig (platform ${key})" >&2
    ota_asset_missing=1
  fi
done < <(jq -r '.platforms | keys[]' <<<"$manifest")
if [[ "$ota_asset_missing" -ne 0 ]]; then
  exit 1
fi

if [[ -n "${REQUIRED_INSTALLER_GLOBS:-}" ]]; then
  missing_installer=0
  for pattern in ${REQUIRED_INSTALLER_GLOBS}; do
    [[ -n "$pattern" ]] || continue
    matched=0
    while IFS= read -r asset; do
      [[ -n "$asset" ]] || continue
      case "$asset" in
        $pattern) matched=1; break ;;
      esac
    done <<<"$asset_names"
    if [[ "$matched" -eq 0 ]]; then
      echo "[verify-release] missing user installer matching pattern: ${pattern}" >&2
      missing_installer=1
    fi
  done
  if [[ "$missing_installer" -ne 0 ]]; then
    exit 1
  fi
fi

if [[ "${REQUIRE_BARE_LINUX_APPIMAGE:-}" == "1" ]]; then
  bare_appimage=0
  while IFS= read -r asset; do
    [[ -n "$asset" ]] || continue
    [[ "$asset" == *.AppImage ]] || continue
    [[ "$asset" == *.AppImage.tar.gz ]] && continue
    bare_appimage=1
    break
  done <<<"$asset_names"
  if [[ "$bare_appimage" -eq 0 ]]; then
    echo "[verify-release] missing bare Linux .AppImage installer on release" >&2
    exit 1
  fi
fi

checksum_ok=0
while IFS= read -r asset; do
  [[ -n "$asset" ]] || continue
  case "$asset" in
    *.dmg|*.exe|*.msi|*.AppImage|*.AppImage.tar.gz|*.deb)
      if require_asset "${asset}.sha256"; then
        checksum_ok=1
      fi
      ;;
  esac
done <<<"$asset_names"

if [[ "$checksum_ok" -eq 0 ]]; then
  echo "[verify-release] no installer .sha256 sidecars found on release" >&2
  exit 1
fi

echo "[verify-release] OK (version=${VERSION}, ota_platforms=${platform_count})"
