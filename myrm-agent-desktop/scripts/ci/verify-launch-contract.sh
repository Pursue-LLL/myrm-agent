#!/usr/bin/env bash
# Static smoke: Desktop Launch Contract invariants (no runtime app required).
set -euo pipefail

DESKTOP_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TAURI_DIR="$DESKTOP_ROOT/src-tauri"
SETUP="$TAURI_DIR/src/app/setup.rs"
CONFIG="$TAURI_DIR/src/config.rs"
SHELL_HTML="$TAURI_DIR/frontend-shell/index.html"
TAURI_CONF="$TAURI_DIR/tauri.conf.json"
PYTHON_BACKEND="$TAURI_DIR/src/runtime/python_backend.rs"
HEALTH_PROBE="$DESKTOP_ROOT/../myrm-agent-frontend/src/lib/backend-health-probe.ts"

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

grep -q 'backend-start-failed' "$SHELL_HTML" \
  || fail "frontend-shell must handle backend-start-failed"

grep -q '"withGlobalTauri": true' "$TAURI_CONF" \
  || fail "tauri.conf.json must enable withGlobalTauri for frontend-shell IPC"

grep -q 'auto_start_webui' "$CONFIG" \
  && fail "auto_start_webui dead field must stay removed"

# The shell kills a sidecar that has not answered /health within its startup budget and then reports
# backend-start-failed. The frontend readiness gate must outlast that budget: giving up earlier reports
# "unreachable" for a backend the shell is still starting.
shell_budget_s="$(sed -n 's/^const BACKEND_STARTUP_TIMEOUT: Duration = Duration::from_secs(\([0-9][0-9]*\));.*/\1/p' "$PYTHON_BACKEND")"
gate_attempts="$(sed -n 's/^export const DESKTOP_BACKEND_HEALTH_MAX_ATTEMPTS = \([0-9][0-9]*\);.*/\1/p' "$HEALTH_PROBE")"
gate_interval_ms="$(sed -n 's/^export const BACKEND_HEALTH_POLL_INTERVAL_MS = \([0-9][0-9]*\);.*/\1/p' "$HEALTH_PROBE")"
[[ -n "$shell_budget_s" && -n "$gate_attempts" && -n "$gate_interval_ms" ]] \
  || fail "cannot read the shell backend startup budget or the frontend desktop readiness budget"
(( gate_attempts * gate_interval_ms > shell_budget_s * 1000 )) \
  || fail "frontend desktop readiness budget (${gate_attempts} x ${gate_interval_ms} ms) must exceed the shell backend startup budget (${shell_budget_s} s)"

echo "[launch-contract] OK"
