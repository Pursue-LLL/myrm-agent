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

fail() {
  echo "CHROME_E2E_FAIL: $*" >&2
  exit 1
}

ok() {
  echo "CHROME_E2E_OK: $*"
}

# 1. Dev servers (Next.js cold compile can exceed 3s)
curl -sf --max-time 30 "$UI_BASE" >/dev/null || fail "Frontend not reachable at $UI_BASE — run: ./myrm start"
curl -sf --max-time 10 "$API_BASE/api/v1/health" >/dev/null || fail "Backend not reachable at $API_BASE — run: ./myrm start"
ok "dev servers :3000/:8080"

# 2. Main Chrome process (not helper-only)
if ! pgrep -f "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" >/dev/null 2>&1; then
  fail "Main Google Chrome is not running — open your signed-in profile"
fi
ok "main Chrome process"

# 3. Structural blockers before CDP freshness (surface all actionable errors early)
if pgrep -lf 'MyrmChromeMcp' >/dev/null 2>&1; then
  fail "MyrmChromeMcp Chrome detected — quit it; use MCP --autoConnect on main Chrome only"
fi
MCP_NPM_COUNT="$(pgrep -f 'npm exec chrome-devtools-mcp' 2>/dev/null | wc -l | tr -d ' ')"
if [[ "${MCP_NPM_COUNT}" -gt 1 ]]; then
  fail "Too many chrome-devtools-mcp processes (${MCP_NPM_COUNT}) — close extra Agent tabs, then Cmd+Q Cursor"
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
  fail "DevToolsActivePort is stale (${port_age}s old) — quit Chrome, reopen, re-enable remote debugging"
fi
raw_port=$(sed -n '1p' "$ACTIVE_PORT_FILE" | tr -d '[:space:]')
ws_path=$(sed -n '2p' "$ACTIVE_PORT_FILE" | tr -d '[:space:]')
if [[ -z "$raw_port" || -z "$ws_path" ]]; then
  fail "Invalid DevToolsActivePort content"
fi
ok "DevToolsActivePort fresh (${port_age}s)"

# 5. WebSocket endpoint (M144+ permission-proxy: HTTP /json/version may 404; WS is the truth)
if command -v python3 >/dev/null 2>&1; then
  python3 - <<PY || fail "CDP WebSocket unreachable on port $raw_port — re-toggle remote debugging Allow"
import asyncio
import sys
try:
    import websockets
except ImportError:
    sys.exit(0)
async def main() -> None:
    uri = f"ws://127.0.0.1:${raw_port}${ws_path}"
    async with websockets.connect(uri, open_timeout=3):
        pass
asyncio.run(main())
PY
  ok "CDP WebSocket ws://127.0.0.1:${raw_port}${ws_path}"
fi

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
