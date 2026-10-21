#!/usr/bin/env bash
# Generate per-asset .sha256 checksums and Tauri updater latest.json for a GitHub Release.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=pick-platform-asset.sh
source "${SCRIPT_DIR}/pick-platform-asset.sh"

TAG="${TAG:?Set TAG to the release tag (e.g. v0.1.13)}"
REPO="${GITHUB_REPOSITORY:?Set GITHUB_REPOSITORY}"

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "$WORK_DIR"' EXIT

cd "$WORK_DIR"
mkdir -p assets
expected_count="$(gh release view "$TAG" --repo "$REPO" --json assets --jq '.assets | length')"
local_count=0
max_attempts=6
shopt -s nullglob
for attempt in $(seq 1 "$max_attempts"); do
  rm -rf assets/*
  gh release download "$TAG" --repo "$REPO" --dir assets
  shopt -s nullglob
  local_count=0
  for f in assets/*; do
    [[ -f "$f" ]] && local_count=$((local_count + 1))
  done
  if [[ "$local_count" -ge "$expected_count" ]]; then
    echo "[finalize-release] downloaded ${local_count}/${expected_count} assets"
    break
  fi
  echo "[finalize-release] assets ${local_count}/${expected_count} (attempt ${attempt}/${max_attempts}), retrying..." >&2
  sleep 10
done

ASSETS=(assets/*)
if [[ ${#ASSETS[@]} -eq 0 || "$local_count" -lt "$expected_count" ]]; then
  echo "[finalize-release] incomplete release download for ${TAG} (${local_count}/${expected_count})" >&2
  exit 1
fi

for file in "${ASSETS[@]}"; do
  base="$(basename "$file")"
  [[ "$base" == *.sha256 ]] && continue
  [[ "$base" == *.sig ]] && continue
  [[ "$base" == "latest.json" ]] && continue
  hash="$(sha256sum "$file" | awk '{print $1}')"
  printf '%s  %s\n' "$hash" "$base" >"assets/${base}.sha256"
  echo "checksum: ${base}.sha256"
done

VERSION="${TAG#v}"
PUB_DATE="$(gh api "repos/${REPO}/releases/tags/${TAG}" --jq '.published_at // empty')"
NOTES="$(gh api "repos/${REPO}/releases/tags/${TAG}" --jq '.body // ""')"

read_asset_signature() {
  local asset_name="$1"
  local sig_path="assets/${asset_name}.sig"
  [[ -f "$sig_path" ]] || return 1
  # Minisign output is a single base64 line; strip trailing newline only.
  local raw
  raw="$(<"$sig_path")"
  printf '%s' "${raw%$'\n'}"
}

build_platform_entry() {
  local url="$1"
  local asset_name="$2"
  local signature=""
  if signature="$(read_asset_signature "$asset_name")"; then
    echo "latest.json signature: ${asset_name}.sig" >&2
    jq -n --arg url "$url" --arg signature "$signature" '{url: $url, signature: $signature}'
  else
    echo "latest.json warning: no .sig for ${asset_name}; OTA signature omitted" >&2
    jq -n --arg url "$url" '{url: $url}'
  fi
}

PLATFORMS_JSON='{}'
required_ota_keys="${REQUIRED_OTA_PLATFORM_KEYS:-}"

is_required_ota_key() {
  local key="$1"
  [[ -z "$required_ota_keys" ]] && return 1
  case " ${required_ota_keys} " in
    *" ${key} "*) return 0 ;;
    *) return 1 ;;
  esac
}

for tauri_key in darwin-aarch64 darwin-x86_64 windows-x86_64 linux-x86_64; do
  if asset_name="$(pick_platform_asset "$tauri_key")"; then
    if ! read_asset_signature "$asset_name" >/dev/null 2>&1; then
      if is_required_ota_key "$tauri_key"; then
        echo "[finalize-release] required OTA platform ${tauri_key} missing .sig for ${asset_name}" >&2
        exit 1
      fi
      echo "latest.json skip: $tauri_key -> ${asset_name} (no .sig; OTA omitted, manual install still available)" >&2
      continue
    fi
    url="https://github.com/${REPO}/releases/download/${TAG}/${asset_name}"
    entry="$(build_platform_entry "$url" "$asset_name")"
    PLATFORMS_JSON="$(jq --arg key "$tauri_key" --argjson entry "$entry" '. + {($key): $entry}' <<<"$PLATFORMS_JSON")"
    echo "latest.json platform: $tauri_key -> $asset_name"
  fi
done

platform_count="$(jq 'keys | length' <<<"$PLATFORMS_JSON")"
if [[ "$platform_count" -eq 0 ]]; then
  echo "No platform assets matched for latest.json (tag=$TAG)" >&2
  exit 1
fi

if [[ -n "$required_ota_keys" ]]; then
  missing_required=0
  for key in ${required_ota_keys}; do
    [[ -n "$key" ]] || continue
    if ! jq -e --arg k "$key" '.[$k]' <<<"$PLATFORMS_JSON" >/dev/null; then
      echo "[finalize-release] missing required OTA platform in latest.json: ${key}" >&2
      missing_required=1
    fi
  done
  if [[ "$missing_required" -ne 0 ]]; then
    exit 1
  fi
fi

jq -n \
  --arg version "$VERSION" \
  --arg notes "$NOTES" \
  --arg pub_date "$PUB_DATE" \
  --argjson platforms "$PLATFORMS_JSON" \
  '{version: $version, notes: $notes, pub_date: $pub_date, platforms: $platforms}' \
  >assets/latest.json

echo "Wrote latest.json (version=$VERSION, platforms=$platform_count)"

UPLOAD=(assets/latest.json)
for checksum in assets/*.sha256; do
  [[ -f "$checksum" ]] && UPLOAD+=("$checksum")
done

gh release upload "$TAG" --repo "$REPO" "${UPLOAD[@]}" --clobber
echo "Uploaded manifest and checksums to $TAG"
