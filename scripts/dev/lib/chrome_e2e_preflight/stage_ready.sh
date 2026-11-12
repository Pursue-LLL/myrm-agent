#!/usr/bin/env bash
# Preflight finish: the attach-mode ready line, the stale-MCP warning, the orchestrator and mux checks and
# the final runtime health snapshot (with the snapshot function only these steps use).
# Sourced by chrome-e2e-preflight.sh at the point where this step starts. It runs in the entry's shell, so
# its globals, `fail` and `exit` are the entry's.
# shellcheck shell=bash
# shellcheck disable=SC2034  # FRONTEND_LOCK is read by lib/frontend-warmup.sh

_print_e2e_health_json() {
  local runtime_py="${SCRIPT_DIR}/lib/e2e_core/runtime_identity.py"
  local require_ready="${1:-0}"
  local shell_hot="false" client_hot="false"
  [[ -f "${runtime_py}" ]] || fail "Missing runtime_identity.py at ${runtime_py}"
  if [[ "$(_frontend_shell_hot_status)" == "yes" ]]; then
    shell_hot="true"
  fi
  if [[ "$(_frontend_client_hot_status)" == "yes" ]]; then
    client_hot="true"
  fi
  local health_args=(
    --auto-probe
    --ui "${UI_BASE}"
    --api "${API_BASE}"
  )
  [[ "${shell_hot}" == "true" ]] && health_args+=(--shell-hot)
  [[ "${client_hot}" == "true" ]] && health_args+=(--client-hot)
  [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]] && health_args+=(--attach-mode)
  if [[ "${require_ready}" == "1" ]]; then
    health_args+=("$(_attach_health_require_args)")
  fi
  "${PREFLIGHT_PY}" "${runtime_py}" "${health_args[@]}"
}

if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
  _heal_shared_ui_if_stale || true
  if [[ "$(_frontend_client_hot_status)" != "yes" ]]; then
    fail "client_hot missing during attach — first Agent must finish ./myrm-dev ready --chrome"
  fi
  echo "CHROME_E2E_READY ui=$UI_BASE api=$API_BASE port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
  CHROME_E2E_CLI="${SCRIPT_DIR}/chrome-e2e/cli.sh"
  if [[ -f "${CHROME_E2E_CLI}" ]]; then
    bash "${CHROME_E2E_CLI}" transition preflight-done "${SAVED_FRONTMOST_PID}" >/dev/null 2>&1 || true
  fi
  _print_e2e_health_json
  exit 0
fi

# 5. CDP WebSocket (Chrome 150+ may omit DevToolsActivePort — use /json/version fallback)
raw_port="${MYRM_CHROME_E2E_PORT}"
ws_path=""
if [[ -f "$ACTIVE_PORT_FILE" ]]; then
  raw_port=$(sed -n '1p' "$ACTIVE_PORT_FILE" | tr -d '[:space:]')
  ws_path=$(sed -n '2p' "$ACTIVE_PORT_FILE" | tr -d '[:space:]')
  if [[ -z "$raw_port" || -z "$ws_path" ]]; then
    fail "Invalid DevToolsActivePort content"
  fi
  ok "DevToolsActivePort port=${raw_port}"
else
  if ! myrm_chrome_e2e_cdp_healthy; then
    fail "CDP not reachable on port ${MYRM_CHROME_E2E_PORT} — run: ./myrm-dev ready --chrome"
  fi
  ok "CDP /json/version port=${MYRM_CHROME_E2E_PORT} (no DevToolsActivePort file)"
fi

if ! command -v "${PREFLIGHT_PY}" >/dev/null 2>&1; then
  fail "python3 required for CDP WebSocket check — install Python 3 or run: cd myrm-agent-server && uv sync"
fi
if [[ -n "${ws_path}" ]]; then
  ws_uri="ws://127.0.0.1:${raw_port}${ws_path}"
else
  ws_uri="$("${PREFLIGHT_PY}" - <<PY
import json
import urllib.request
data = json.load(urllib.request.urlopen("http://127.0.0.1:${MYRM_CHROME_E2E_PORT}/json/version", timeout=5))
print(data["webSocketDebuggerUrl"])
PY
)"
fi
export WS_URI="${ws_uri}"
"${PREFLIGHT_PY}" - <<'PY' || fail "CDP WebSocket unreachable — run: ./myrm-dev ready --chrome"
import asyncio
import os
import sys
try:
    import websockets
except ImportError:
    print("websockets package required in server venv — run: cd myrm-agent-server && uv sync", file=sys.stderr)
    sys.exit(1)
async def main() -> None:
    uri = os.environ["WS_URI"]
    async with websockets.connect(uri, open_timeout=10):
        pass
asyncio.run(main())
PY
ok "CDP WebSocket ${ws_uri}"

# 7. Client hydration warmup (Turbopack chunk graph — not covered by curl shell_hot)
if ! _warmup_frontend_client; then
  fail "frontend client_hot warmup failed — see STACK_FAIL above"
fi
ok "frontend client_hot"

# Client warmup can take long enough for a damaged upstream MCP process to
# disappear. Re-check immediately before declaring the stack ready so callers
# never receive a stale READY signal.
if [[ "${MUX_USING}" -eq 1 ]]; then
  _ensure_mux_upstream
fi

# 8. Stale chrome-devtools-mcp from old Cursor sessions
if pgrep -fl "chrome-devtools-mcp" >/dev/null 2>&1; then
  while read -r line; do
    pid=$(echo "$line" | awk '{print $1}')
    if [[ -n "$pid" && "$pid" =~ ^[0-9]+$ ]]; then
      etime=$(ps -p "$pid" -o etime= 2>/dev/null | tr -d ' ')
      if [[ "$etime" =~ ^[0-9]+-[0-9]+: ]]; then
        echo "CHROME_E2E_WARN: stale chrome-devtools-mcp pid=$pid etime=$etime — Cmd+Q restart Cursor before MCP E2E" >&2
      fi
    fi
  done < <(pgrep -lf "chrome-devtools-mcp" 2>/dev/null || true)
fi

echo "CHROME_E2E_READY ui=$UI_BASE api=$API_BASE port=$raw_port profile=${MYRM_CHROME_E2E_DATA_DIR}"
CHROME_E2E_CLI="${SCRIPT_DIR}/chrome-e2e/cli.sh"
if [[ -f "${CHROME_E2E_CLI}" ]]; then
  bash "${CHROME_E2E_CLI}" transition preflight-done "${SAVED_FRONTMOST_PID}" >/dev/null 2>&1 || true
fi
if [[ "${MYRM_CHROME_E2E_ATTACH}" != "1" ]]; then
  _ensure_stack_epoch_file
fi
export_myrm_next_dist_dir
FRONTEND_LOCK="$(resolve_frontend_lock_path "${FRONTEND_DIR}")"

# TAB-5: idle blank prune SSOT is coordinator IdleHygieneScheduler (reap/finish/teardown).
# Preflight must not run parallel prune hooks — they raced BODY leases and masked orphan storms.

if [[ "${MYRM_BROWSER_ORCHESTRATOR:-}" == "1" ]]; then
  _ensure_browser_orchestrator_after_data_plane
  if [[ "${MYRM_CHROME_E2E_ATTACH:-}" != "1" ]] && declare -f _mux_daemon_count >/dev/null 2>&1; then
    mux_count="$(_mux_daemon_count 2>/dev/null || echo 0)"
    if [[ "${mux_count}" != "1" ]]; then
      _restart_mux_safely "orchestrator preflight: expected one mux daemon, found ${mux_count}"
      sleep 1
      mux_count="$(_mux_daemon_count 2>/dev/null || echo 0)"
      [[ "${mux_count}" == "1" ]] || fail "mux daemon count=${mux_count} after reconcile — Cmd+Q Cursor, then: ./myrm-dev ready --chrome"
    fi
  fi
fi

health_attempt=0
while [[ "${health_attempt}" -lt 3 ]]; do
  if _print_e2e_health_json 1; then
    exit 0
  fi
  health_attempt=$((health_attempt + 1))
  if [[ "${health_attempt}" -lt 3 ]]; then
    echo "CHROME_E2E_WARN: health snapshot retry ${health_attempt}/3" >&2
    sleep 2
  fi
done
fail "final runtime health snapshot rejected — retry: ./myrm-dev ready --chrome"
