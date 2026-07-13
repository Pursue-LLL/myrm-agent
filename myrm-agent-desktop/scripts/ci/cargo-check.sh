#!/usr/bin/env bash
# Desktop Rust compile gate: stub sidecars → cargo check → config unit tests.
set -euo pipefail

DESKTOP_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPO_ROOT="$(cd "$DESKTOP_ROOT/.." && pwd)"
TAURI_DIR="$DESKTOP_ROOT/src-tauri"
FRONTEND_STANDALONE="$REPO_ROOT/myrm-agent-frontend/.next/standalone/myrm-agent-frontend"

bash "$REPO_ROOT/scripts/ci/desktop-release/prepare-check-stub-sidecars.sh"

mkdir -p "$FRONTEND_STANDALONE"
if [[ ! -f "$FRONTEND_STANDALONE/server.js" ]]; then
  printf '%s\n' '// CI stub for cargo check' >"$FRONTEND_STANDALONE/server.js"
  echo "[desktop-cargo-check] stub frontend standalone at $FRONTEND_STANDALONE"
fi

cd "$TAURI_DIR"
cargo check --locked
cargo test config::tests -- --nocapture

echo "[desktop-cargo-check] OK"
