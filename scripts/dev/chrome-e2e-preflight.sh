#!/usr/bin/env bash
# Chrome MCP E2E preflight — run before chrome-devtools new_page on :3000.
# Exit 0 prints CHROME_E2E_READY; exit 1 prints actionable failures.
set -euo pipefail

UI_BASE="${E2E_UI_BASE:-http://127.0.0.1:3000}"
API_BASE="${E2E_API_BASE:-http://127.0.0.1:8080}"
CHROME_DATA_DIR="${CHROME_DATA_DIR:-$HOME/Library/Application Support/Google/Chrome}"
ACTIVE_PORT_FILE="$CHROME_DATA_DIR/DevToolsActivePort"
MAX_PORT_AGE_SEC="${CHROME_E2E_MAX_PORT_AGE_SEC:-300}"
STALE_MCP_AGE_SEC="${CHROME_E2E_STALE_MCP_AGE_SEC:-3600}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
MONOREPO_ROOT="$(cd "${AGENT_ROOT}/.." && pwd)"
MUX_BIN="${MONOREPO_ROOT}/scripts/dev/cdmcp-mux-autoconnect/bin/cdmcp-mux-autoconnect.mjs"
SERVER_DIR="${AGENT_ROOT}/myrm-agent-server"
PREFLIGHT_PY="${SERVER_DIR}/.venv/bin/python"
if [[ ! -x "${PREFLIGHT_PY}" ]]; then
  PREFLIGHT_PY="python3"
fi

fail() {
  echo "CHROME_E2E_FAIL: $*" >&2
  exit 1
}

ok() {
  echo "CHROME_E2E_OK: $*"
}

# 1. Dev servers (Next.js cold compile can exceed 3s)
curl -sf --max-time 30 "$UI_BASE" >/dev/null || fail "Frontend not reachable at $UI_BASE — run: cd open-perplexity && ./myrm ready"
curl -sf --max-time 10 "$API_BASE/api/v1/health" >/dev/null || fail "Backend not reachable at $API_BASE — run: cd open-perplexity && ./myrm ready"
ok "dev servers :3000/:8080"

# 2. Main Chrome process (not helper-only)
if ! pgrep -f "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" >/dev/null 2>&1; then
  fail "Main Google Chrome is not running — open your signed-in profile"
fi
ok "main Chrome process"

# 3. Structural blockers before CDP freshness (surface all actionable errors early)
if pgrep -lf 'MyrmChromeMcp' >/dev/null 2>&1; then
  fail "MyrmChromeMcp Chrome detected — quit it; use mux shim on main Chrome only"
fi
MUX_STATE_DIR="${CDMCP_MUX_STATE_DIR:-$HOME/.local/state/cdmcp-mux}"
MUX_PID_FILE="${MUX_STATE_DIR}/daemon.pid"
MUX_USING=0
if grep -q 'cdmcp-mux-autoconnect' "${HOME}/.cursor/mcp.json" 2>/dev/null \
  || grep -q 'cdmcp-mux-autoconnect' "${HOME}/.cursor-3.1.15/mcp.json" 2>/dev/null \
  || pgrep -f 'cdmcp-mux-autoconnect' >/dev/null 2>&1 \
  || [[ -f "${MUX_PID_FILE}" ]]; then
  MUX_USING=1
fi
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
if lsof -iTCP:9333 -sTCP:LISTEN >/dev/null 2>&1; then
  echo "CHROME_E2E_WARN: port 9333 listening (MyrmChromeE2E?) — quit non-main Chrome to avoid conflicts" >&2
fi

# 4. DevToolsActivePort freshness
if [[ ! -f "$ACTIVE_PORT_FILE" ]]; then
  fail "DevToolsActivePort missing — enable chrome://inspect/#remote-debugging → Allow"
fi
port_age=$(( $(date +%s) - $(stat -f %m "$ACTIVE_PORT_FILE" 2>/dev/null || stat -c %Y "$ACTIVE_PORT_FILE") ))
if (( port_age > MAX_PORT_AGE_SEC )); then
  echo "CHROME_E2E_WARN: DevToolsActivePort mtime is ${port_age}s old — verifying CDP WebSocket" >&2
else
  ok "DevToolsActivePort fresh (${port_age}s)"
fi
raw_port=$(sed -n '1p' "$ACTIVE_PORT_FILE" | tr -d '[:space:]')
ws_path=$(sed -n '2p' "$ACTIVE_PORT_FILE" | tr -d '[:space:]')
if [[ -z "$raw_port" || -z "$ws_path" ]]; then
  fail "Invalid DevToolsActivePort content"
fi

# 5. WebSocket endpoint (M144+ permission-proxy: HTTP /json/version may 404; WS is the truth)
if ! command -v "${PREFLIGHT_PY}" >/dev/null 2>&1; then
  fail "python3 required for CDP WebSocket check — install Python 3 or run: cd myrm-agent-server && uv sync"
fi
"${PREFLIGHT_PY}" - <<PY || fail "CDP WebSocket unreachable on port $raw_port — re-toggle remote debugging Allow"
import asyncio
import sys
try:
    import websockets
except ImportError:
    print("websockets package required in server venv — run: cd myrm-agent-server && uv sync", file=sys.stderr)
    sys.exit(1)
async def main() -> None:
    uri = f"ws://127.0.0.1:${raw_port}${ws_path}"
    async with websockets.connect(uri, open_timeout=10):
        pass
asyncio.run(main())
PY
ok "CDP WebSocket ws://127.0.0.1:${raw_port}${ws_path}"

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

echo "CHROME_E2E_READY ui=$UI_BASE api=$API_BASE port=$raw_port"
exit 0
