#!/usr/bin/env bash
# Advisory gate: detect pubkey/signing-secret mismatch before desktop release builds.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CONF="${ROOT}/myrm-agent-desktop/src-tauri/tauri.conf.json"

if [[ ! -f "$CONF" ]]; then
  echo "[check-updater-pubkey] Missing ${CONF}" >&2
  exit 1
fi

pubkey="$(jq -r '.plugins.updater.pubkey // ""' "$CONF")"
is_placeholder=false
if [[ -z "$pubkey" || "$pubkey" == *"PLACEHOLDER"* ]]; then
  is_placeholder=true
fi

if [[ "$is_placeholder" == true && -n "${TAURI_SIGNING_PRIVATE_KEY:-}" ]]; then
  echo "[check-updater-pubkey] ERROR: TAURI_SIGNING_PRIVATE_KEY is set but pubkey is still a placeholder." >&2
  echo "[check-updater-pubkey] Paste the .key.pub into tauri.conf.json#plugins.updater.pubkey (see SIGNING.md)." >&2
  exit 1
fi

if [[ "$is_placeholder" == true ]]; then
  echo "::warning title=Updater pubkey placeholder::OTA is disabled until SIGNING.md steps complete. Installers still publish."
  exit 0
fi

if [[ -z "${TAURI_SIGNING_PRIVATE_KEY:-}" ]]; then
  echo "::warning title=Updater signing secret missing::Pubkey is configured but TAURI_SIGNING_PRIVATE_KEY is unset; bundles will not be signed for OTA."
fi

echo "[check-updater-pubkey] Updater pubkey configured."
