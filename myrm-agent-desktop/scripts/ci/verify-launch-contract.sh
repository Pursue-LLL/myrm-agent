#!/usr/bin/env bash
# Static smoke: Desktop Launch Contract invariants (no runtime app required).
set -euo pipefail

DESKTOP_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TAURI_DIR="$DESKTOP_ROOT/src-tauri"
SETUP="$TAURI_DIR/src/app/setup.rs"
CONFIG="$TAURI_DIR/src/config.rs"
SHELL_HTML="$TAURI_DIR/frontend-shell/index.html"
TAURI_CONF="$TAURI_DIR/tauri.conf.json"

fail() {
  echo "[launch-contract] FAIL: $1" >&2
  exit 1
}

grep -q 'start_frontend(app_handle.clone(), frontend_state, frontend_config)' "$SETUP" \
  || fail "setup.rs must always call start_frontend"

if grep -q 'if system_config_clone.enable_webui_mode' "$SETUP" \
  && grep -A20 'if system_config_clone.enable_webui_mode' "$SETUP" | grep -q 'start_frontend'; then
  fail "start_frontend must not be gated by enable_webui_mode"
fi

grep -q 'api_port: backend.port' "$CONFIG" \
  || fail "FrontendConfig.api_port must follow BackendConfig.port"

grep -q 'load_system_config' "$SHELL_HTML" \
  || fail "frontend-shell must read webui port via load_system_config"

grep -q 'frontend-start-failed' "$SHELL_HTML" \
  || fail "frontend-shell must handle frontend-start-failed"

grep -q '"withGlobalTauri": true' "$TAURI_CONF" \
  || fail "tauri.conf.json must enable withGlobalTauri for frontend-shell IPC"

grep -q 'auto_start_webui' "$CONFIG" \
  && fail "auto_start_webui dead field must stay removed"

echo "[launch-contract] OK"
