#!/usr/bin/env bash
# Chrome MCP E2E preflight — dedicated Myrm E2E Chrome (:9333, zero Allow).
# Exit 0 prints CHROME_E2E_READY; exit 1 prints actionable failures.
set -euo pipefail

UI_BASE="${E2E_UI_BASE:-http://127.0.0.1:3000}"
API_BASE="${E2E_API_BASE:-http://127.0.0.1:8080}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=myrm-chrome-e2e-lib.sh
source "${SCRIPT_DIR}/myrm-chrome-e2e-lib.sh"

AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MONOREPO_ROOT="$(cd "${AGENT_ROOT}/.." && pwd)"
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

# 1. Dev servers (Next.js cold compile can exceed 3s)
if ! curl -sf --max-time 30 "$UI_BASE" >/dev/null; then
  if [[ -f "${AGENT_ROOT}/scripts/dev/dev-stack.sh" ]]; then
    echo "CHROME_E2E_WARN: frontend down — running dev-stack ensure" >&2
    bash "${AGENT_ROOT}/scripts/dev/dev-stack.sh" ensure || true
  fi
  curl -sf --max-time 30 "$UI_BASE" >/dev/null || fail "Frontend not reachable at $UI_BASE — run: cd open-perplexity && ./myrm ready"
fi
if ! curl -sf --max-time 10 "$API_BASE/api/v1/health" >/dev/null; then
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
if ! ensure_out="$(bash "${ENSURE_CHROME}" 2>&1)"; then
  echo "${ensure_out}" >&2
  fail "Myrm E2E Chrome failed to start — see MYRM_CHROME_E2E_FAIL above"
fi
echo "${ensure_out}"
chrome_just_started=0
if [[ "${ensure_out}" == *"MYRM_CHROME_E2E_START:"* ]]; then
  chrome_just_started=1
fi
ok "Myrm E2E Chrome port=${MYRM_CHROME_E2E_PORT}"

ACTIVE_PORT_FILE="${MYRM_CHROME_E2E_ACTIVE_PORT_FILE}"

# 4. mux daemon (parallel Agent tabs)
MUX_STATE_DIR="${CDMCP_MUX_STATE_DIR:-$HOME/.local/state/cdmcp-mux}"
MUX_PID_FILE="${MUX_STATE_DIR}/daemon.pid"
MUX_USING=0
if grep -q 'cdmcp-mux-autoconnect' "${HOME}/.cursor/mcp.json" 2>/dev/null \
  || grep -q 'cdmcp-mux-autoconnect' "${HOME}/.cursor-3.1.15/mcp.json" 2>/dev/null \
  || pgrep -f 'cdmcp-mux-autoconnect' >/dev/null 2>&1 \
  || [[ -f "${MUX_PID_FILE}" ]]; then
  MUX_USING=1
fi

_stop_mux_daemon() {
  [[ -f "${MUX_PID_FILE}" ]] || return 0
  local pid
  pid="$(tr -d '[:space:]' < "${MUX_PID_FILE}")"
  if [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null; then
    kill "${pid}" 2>/dev/null || true
    sleep 0.5
  fi
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
  echo "CHROME_E2E_WARN: starting cdmcp-mux daemon for preflight" >&2
  CHROME_DATA_DIR="${MYRM_CHROME_E2E_DATA_DIR}" \
  MYRM_CHROME_E2E_DATA_DIR="${MYRM_CHROME_E2E_DATA_DIR}" \
  MYRM_CHROME_E2E_PORT="${MYRM_CHROME_E2E_PORT}" \
    node "${MUX_BIN}" daemon >/dev/null 2>&1 &
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

if [[ "${MUX_USING}" -eq 1 && "${chrome_just_started}" -eq 1 ]]; then
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

# 6. Stale chrome-devtools-mcp from old Cursor sessions
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
exit 0
