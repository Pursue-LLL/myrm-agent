#!/usr/bin/env bash
# Chrome MCP E2E preflight — dedicated Myrm E2E Chrome (:9333, zero Allow).
# Exit 0 prints CHROME_E2E_READY; exit 1 prints actionable failures.
set -euo pipefail

UI_BASE="${E2E_UI_BASE:-http://127.0.0.1:3000}"
API_BASE="${E2E_API_BASE:-http://127.0.0.1:8080}"
MYRM_CHROME_E2E_ATTACH="${MYRM_CHROME_E2E_ATTACH:-0}"
export MYRM_CHROME_E2E_ATTACH

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=myrm-chrome-e2e-lib.sh
source "${SCRIPT_DIR}/myrm-chrome-e2e-lib.sh"

AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MONOREPO_ROOT="$(cd "${AGENT_ROOT}/.." && pwd)"
STATE_DIR="${MYRM_DEV_STATE_DIR:-${HOME}/.local/state/myrm-dev}"
FRONTEND_DIR="${AGENT_ROOT}/myrm-agent-frontend"
FRONTEND_LOCK="${FRONTEND_DIR}/.next/dev-server.lock"
FRONTEND_LOG="${FRONTEND_DIR}/.myrm-dev-frontend.log"
APP_URL="${UI_BASE}"
FRONTEND_PORT=3000
# shellcheck source=lib/frontend-warmup.sh
source "${SCRIPT_DIR}/lib/frontend-warmup.sh"
# shellcheck source=lib/stack-epoch.sh
source "${SCRIPT_DIR}/lib/stack-epoch.sh"
MUX_BIN="${MONOREPO_ROOT}/scripts/dev/cdmcp-mux-autoconnect/bin/cdmcp-mux-autoconnect.mjs"
ENSURE_CHROME="${SCRIPT_DIR}/ensure-myrm-chrome-e2e.sh"
SERVER_DIR="${AGENT_ROOT}/myrm-agent-server"
PREFLIGHT_PY="${SERVER_DIR}/.venv/bin/python"
if [[ ! -x "${PREFLIGHT_PY}" ]]; then
  PREFLIGHT_PY="python3"
fi

export MYRM_CHROME_E2E_DATA_DIR
export MYRM_CHROME_E2E_PORT
export CHROME_DATA_DIR="${MYRM_CHROME_E2E_DATA_DIR}"

fail() {
  echo "CHROME_E2E_FAIL: $*" >&2
  exit 1
}

ok() {
  echo "CHROME_E2E_OK: $*"
}

_ensure_stack_epoch_file() {
  local epoch_file backend_pid
  epoch_file="$(_stack_epoch_file)"
  if [[ -f "${epoch_file}" ]]; then
    return 0
  fi
  if ! curl -sf --max-time 5 "${API_BASE}/api/v1/health" >/dev/null 2>&1; then
    return 0
  fi
  backend_pid=""
  if [[ -f "${SERVER_DIR}/.myrm-dev-backend.pid" ]]; then
    backend_pid="$(tr -d '[:space:]' <"${SERVER_DIR}/.myrm-dev-backend.pid")"
  fi
  _bump_stack_epoch "${backend_pid}" "${SERVER_DIR}" >/dev/null || true
}

# 1. Dev servers (Next.js cold compile can exceed 3s)
if ! curl -sf --max-time 30 "$UI_BASE" >/dev/null; then
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
    fail "Frontend not reachable at $UI_BASE — first Agent must run: ./myrm ready --chrome"
  fi
  if [[ -f "${AGENT_ROOT}/scripts/dev/dev-stack.sh" ]]; then
    echo "CHROME_E2E_WARN: frontend down — running dev-stack ensure" >&2
    bash "${AGENT_ROOT}/scripts/dev/dev-stack.sh" ensure || true
  fi
  curl -sf --max-time 30 "$UI_BASE" >/dev/null || fail "Frontend not reachable at $UI_BASE — run: cd open-perplexity && ./myrm ready"
fi
if ! curl -sf --max-time 10 "$API_BASE/api/v1/health" >/dev/null; then
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
    fail "Backend not reachable at $API_BASE — first Agent must run: ./myrm ready --chrome"
  fi
  if [[ -f "${AGENT_ROOT}/scripts/dev/dev-stack.sh" ]]; then
    echo "CHROME_E2E_WARN: backend down — running dev-stack ensure" >&2
    bash "${AGENT_ROOT}/scripts/dev/dev-stack.sh" ensure || true
  fi
  curl -sf --max-time 10 "$API_BASE/api/v1/health" >/dev/null || fail "Backend not reachable at $API_BASE — run: cd open-perplexity && ./myrm ready"
fi
ok "dev servers :3000/:8080"

# 2. Legacy second Chrome / debug launchers
if pgrep -lf 'MyrmChromeMcp' >/dev/null 2>&1; then
  fail "MyrmChromeMcp Chrome detected — quit it; use ./myrm ready --chrome (Myrm E2E profile on :9333)"
fi

# 3. Ensure dedicated E2E Chrome (no Allow — launched with --remote-debugging-port)
[[ -f "${ENSURE_CHROME}" ]] || fail "Missing ${ENSURE_CHROME}"
ensure_out=""
if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
  myrm_chrome_e2e_cdp_healthy || fail "Myrm E2E Chrome CDP not reachable — first Agent must run: ./myrm ready --chrome"
  ensure_out="MYRM_CHROME_E2E_ATTACH: existing CDP port=${MYRM_CHROME_E2E_PORT}"
elif ! ensure_out="$(bash "${ENSURE_CHROME}" 2>&1)"; then
  echo "${ensure_out}" >&2
  fail "Myrm E2E Chrome failed to start — see MYRM_CHROME_E2E_FAIL above"
fi
echo "${ensure_out}"
chrome_just_started=0
if [[ "${ensure_out}" == *"MYRM_CHROME_E2E_START:"* ]]; then
  chrome_just_started=1
fi
ok "Myrm E2E Chrome port=${MYRM_CHROME_E2E_PORT}"

PRUNE_SCRIPT="${SCRIPT_DIR}/prune-myrm-chrome-e2e-blank-tabs.sh"
if [[ "${MYRM_CHROME_E2E_ATTACH}" != "1" && -f "${PRUNE_SCRIPT}" ]]; then
  export MYRM_CHROME_E2E_PORT
  if prune_out="$(bash "${PRUNE_SCRIPT}" 2>&1)"; then
    echo "${prune_out}"
    ok "orphan blank tabs pruned"
  else
    echo "CHROME_E2E_WARN: prune failed — ${prune_out}" >&2
  fi
fi

ACTIVE_PORT_FILE="${MYRM_CHROME_E2E_ACTIVE_PORT_FILE}"

# 4. mux daemon (parallel Agent tabs)
MUX_STATE_DIR="${CDMCP_MUX_STATE_DIR:-$HOME/.local/state/cdmcp-mux}"
MUX_PID_FILE="${MUX_STATE_DIR}/daemon.pid"
MUX_LOG_FILE="${MUX_STATE_DIR}/mux.log"
MUX_START_LOCK_DIR="${MUX_STATE_DIR}/daemon.start.lock"
MUX_USING=0
if grep -q 'cdmcp-mux-autoconnect' "${HOME}/.cursor/mcp.json" 2>/dev/null \
  || grep -q 'cdmcp-mux-autoconnect' "${HOME}/.cursor-3.1.15/mcp.json" 2>/dev/null \
  || pgrep -f 'cdmcp-mux-autoconnect' >/dev/null 2>&1 \
  || [[ -f "${MUX_PID_FILE}" ]]; then
  MUX_USING=1
fi

_kill_all_mux_daemons() {
  local pids
  pids="$(pgrep -f 'cdmcp-mux-autoconnect\.mjs daemon' 2>/dev/null | tr '\n' ' ' || true)"
  if [[ -n "${pids// }" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 0.5
  fi
  rm -f "${MUX_PID_FILE}"
}

_stop_mux_daemon() {
  _kill_all_mux_daemons
}

_start_mux_daemon() {
  mkdir -p "${MUX_STATE_DIR}"
  if ! mkdir "${MUX_START_LOCK_DIR}" 2>/dev/null; then
    return 0
  fi
  # The preflight shell exits immediately after readiness. Detached stdio is
  # required so the shared mux survives that shell and remains available to
  # every later Chrome DevTools MCP client.
  nohup env \
    CHROME_DATA_DIR="${MYRM_CHROME_E2E_DATA_DIR}" \
    MYRM_CHROME_E2E_DATA_DIR="${MYRM_CHROME_E2E_DATA_DIR}" \
    MYRM_CHROME_E2E_PORT="${MYRM_CHROME_E2E_PORT}" \
    MCP_MUX_UPSTREAM_STDERR="${MCP_MUX_UPSTREAM_STDERR:-1}" \
    node "${MUX_BIN}" daemon \
    >>"${MUX_LOG_FILE}" 2>&1 < /dev/null &
  local i
  for i in $(seq 1 15); do
    if [[ -f "${MUX_PID_FILE}" ]] && kill -0 "$(tr -d '[:space:]' < "${MUX_PID_FILE}")" 2>/dev/null; then
      rmdir "${MUX_START_LOCK_DIR}" 2>/dev/null || true
      return 0
    fi
    sleep 1
  done
  rmdir "${MUX_START_LOCK_DIR}" 2>/dev/null || true
}

MUX_WS_STAMP="${MUX_STATE_DIR}/upstream-ws-url"

_current_cdp_ws_url() {
  MYRM_CHROME_E2E_PORT="${MYRM_CHROME_E2E_PORT}" "${PREFLIGHT_PY}" - <<'PY'
import json
import os
import urllib.request

port = os.environ.get("MYRM_CHROME_E2E_PORT", "9333")
with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5) as resp:
    data = json.load(resp)
ws = data.get("webSocketDebuggerUrl")
if not isinstance(ws, str) or not ws.startswith("ws://"):
    raise SystemExit("missing webSocketDebuggerUrl")
print(ws)
PY
}

_mux_ws_stamp_matches() {
  [[ -f "${MUX_WS_STAMP}" ]] || return 1
  local current stored
  current="$(_current_cdp_ws_url 2>/dev/null)" || return 1
  stored="$(tr -d '[:space:]' < "${MUX_WS_STAMP}")"
  [[ -n "${stored}" && "${current}" == "${stored}" ]]
}

_stamp_mux_ws_url() {
  local current
  current="$(_current_cdp_ws_url)" || return 1
  mkdir -p "${MUX_STATE_DIR}"
  printf '%s\n' "${current}" >"${MUX_WS_STAMP}"
}

_mux_upstream_ready() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  [[ -f "${MUX_BIN}" ]] || return 1
  local status_json ready
  status_json="$(node "${MUX_BIN}" status 2>/dev/null)" || return 1
  ready="$("${PREFLIGHT_PY}" -c "
import json, sys
try:
    d = json.loads(sys.argv[1])
    print('1' if d.get('upstreamReady') else '0')
except Exception:
    print('0')
" "${status_json}" 2>/dev/null)" || ready=0
  [[ "${ready}" == "1" ]]
}

_ensure_mux_upstream() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  if _mux_ws_stamp_matches && _mux_upstream_ready; then
    return 0
  fi
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
    fail "mux not ready for parallel attach (upstreamReady or CDP ws drift) — first Agent must run: ./myrm ready --chrome"
  fi
  if ! _mux_ws_stamp_matches; then
    echo "CHROME_E2E_WARN: Chrome CDP WebSocket drifted — mux must reconnect (common after Chrome/Cursor restart)" >&2
  else
    echo "CHROME_E2E_WARN: mux upstreamReady=false — MCP list_pages/new_page will hang; restarting daemon" >&2
  fi
  _stop_mux_daemon
  _start_mux_daemon
  local i
  for i in $(seq 1 15); do
    sleep 1
    if _mux_upstream_ready; then
      _stamp_mux_ws_url || true
      ok "cdmcp-mux upstream reconnected"
      return 0
    fi
  done
  fail "cdmcp-mux upstreamReady still false — Cmd+Q Cursor, then: ./myrm ready --chrome"
}

_ensure_mux_daemon() {
  [[ "${MUX_USING}" -eq 1 ]] || return 0
  [[ -f "${MUX_BIN}" ]] || fail "Missing mux bin ${MUX_BIN} — run: bash scripts/dev/install-cdmcp-mux-autoconnect.sh"
  if [[ -f "${MUX_PID_FILE}" ]]; then
    local pid
    pid="$(tr -d '[:space:]' < "${MUX_PID_FILE}")"
    if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
      return 0
    fi
  fi
  if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
    fail "cdmcp-mux daemon not running during attach — first Agent must run: ./myrm ready --chrome"
  fi
  echo "CHROME_E2E_WARN: starting cdmcp-mux daemon for preflight" >&2
  _start_mux_daemon
  local i
  for i in $(seq 1 15); do
    if [[ -f "${MUX_PID_FILE}" ]] && kill -0 "$(tr -d '[:space:]' < "${MUX_PID_FILE}")" 2>/dev/null; then
      ok "cdmcp-mux daemon auto-started"
      return 0
    fi
    sleep 1
  done
  fail "cdmcp-mux daemon failed to start — run: node scripts/dev/cdmcp-mux-autoconnect/bin/cdmcp-mux-autoconnect.mjs daemon"
}

if [[ "${MUX_USING}" -eq 1 && "${chrome_just_started}" -eq 1 && "${MYRM_CHROME_E2E_ATTACH}" != "1" ]]; then
  echo "CHROME_E2E_WARN: E2E Chrome freshly started — restarting mux daemon for new CDP endpoint" >&2
  _stop_mux_daemon
fi
_ensure_mux_daemon

VANILLA_MCP_COUNT=0
if pgrep -f 'npm exec chrome-devtools-mcp' >/dev/null 2>&1; then
  VANILLA_MCP_COUNT="$(pgrep -f 'npm exec chrome-devtools-mcp' | wc -l | tr -d ' ')"
fi
if [[ "${MUX_USING}" -eq 1 ]]; then
  if [[ "${VANILLA_MCP_COUNT}" -gt 0 ]]; then
    fail "Legacy vanilla chrome-devtools-mcp still running (${VANILLA_MCP_COUNT}) — Cmd+Q Cursor, run scripts/dev/enable-chrome-devtools-mcp.sh, reopen"
  fi
  if [[ ! -f "${MUX_PID_FILE}" ]]; then
    fail "cdmcp-mux daemon not running — open any Agent with chrome-devtools MCP once, or run: node scripts/dev/cdmcp-mux-autoconnect/bin/cdmcp-mux-autoconnect.mjs daemon"
  fi
  mux_pid="$(tr -d '[:space:]' < "${MUX_PID_FILE}")"
  if ! kill -0 "${mux_pid}" 2>/dev/null; then
    fail "cdmcp-mux daemon pid ${mux_pid} not alive — Cmd+Q Cursor and reopen"
  fi
  _ensure_mux_upstream
  mux_count="$(pgrep -f 'cdmcp-mux-autoconnect\.mjs daemon' 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${mux_count}" != "1" ]]; then
    if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]]; then
      fail "mux daemon count=${mux_count} during attach — first Agent: ./myrm ready --chrome (attach must not kill mux)"
    fi
    echo "CHROME_E2E_WARN: expected 1 mux daemon, found ${mux_count} — reconciling" >&2
    _kill_all_mux_daemons
    _start_mux_daemon
    sleep 1
    _ensure_mux_upstream
    mux_count="$(pgrep -f 'cdmcp-mux-autoconnect\.mjs daemon' 2>/dev/null | wc -l | tr -d ' ')"
    [[ "${mux_count}" == "1" ]] || fail "mux daemon count=${mux_count} after reconcile — Cmd+Q Cursor, then: ./myrm ready --chrome"
  fi
  ok "cdmcp-mux daemon pid=${mux_pid} (parallel Agent tabs OK)"
else
  if [[ "${VANILLA_MCP_COUNT}" -gt 1 ]]; then
    fail "Too many vanilla chrome-devtools-mcp processes (${VANILLA_MCP_COUNT}) — enable mux: scripts/dev/enable-chrome-devtools-mcp.sh"
  fi
  if [[ "${VANILLA_MCP_COUNT}" -eq 1 ]]; then
    echo "CHROME_E2E_WARN: vanilla chrome-devtools-mcp detected — parallel Agent tabs will collide; run scripts/dev/enable-chrome-devtools-mcp.sh" >&2
  fi
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
    fail "CDP not reachable on port ${MYRM_CHROME_E2E_PORT} — run: ./myrm ready --chrome"
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
"${PREFLIGHT_PY}" - <<'PY' || fail "CDP WebSocket unreachable — run: ./myrm ready --chrome"
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

_print_e2e_health_json() {
  local runtime_py="${SCRIPT_DIR}/lib/runtime_identity.py"
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
  "${PREFLIGHT_PY}" "${runtime_py}" "${health_args[@]}"
}

echo "CHROME_E2E_READY ui=$UI_BASE api=$API_BASE port=$raw_port profile=${MYRM_CHROME_E2E_DATA_DIR}"
if [[ "${MYRM_CHROME_E2E_ATTACH}" != "1" ]]; then
  _ensure_stack_epoch_file
fi
_print_e2e_health_json
exit 0
