#!/usr/bin/env bash
# Create minimal executable stubs so `cargo check` can resolve tauri externalBin paths in CI.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
BIN_DIR="$ROOT/myrm-agent-desktop/src-tauri/binaries"
mkdir -p "$BIN_DIR"

host="$(rustc -vV | sed -n 's/^host: //p')"

create_stub() {
  local path="$1"
  if [[ -x "$path" ]]; then
    return
  fi
  printf '#!/bin/sh\nexit 0\n' >"$path"
  chmod +x "$path"
  echo "[stub-sidecars] $path"
}

create_stub "$BIN_DIR/myrmagent-backend-${host}"
create_stub "$BIN_DIR/agent-runner-${host}"
