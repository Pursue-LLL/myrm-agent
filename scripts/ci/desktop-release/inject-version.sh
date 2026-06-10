#!/usr/bin/env bash
# Inject semantic version from git tag into tauri.conf.json (strip leading "v").
set -euo pipefail

TAG_NAME="${1:-${GITHUB_REF_NAME:-}}"
if [[ -z "$TAG_NAME" ]]; then
  echo "Usage: inject-version.sh <tag> (e.g. v0.1.13)" >&2
  exit 1
fi

VERSION="${TAG_NAME#v}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
CONF="$ROOT/myrm-agent-desktop/src-tauri/tauri.conf.json"

if [[ ! -f "$CONF" ]]; then
  echo "tauri.conf.json not found: $CONF" >&2
  exit 1
fi

TMP="$(mktemp)"
jq --arg version "$VERSION" '.version = $version' "$CONF" >"$TMP"
mv "$TMP" "$CONF"
echo "Injected tauri version: $VERSION (from $TAG_NAME)"
