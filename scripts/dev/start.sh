#!/usr/bin/env bash
# Backend :8080 + frontend dev server :3000 (both background).
# Usage: myrm start
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
# shellcheck source=lib/backend_bg.sh
source "${SCRIPT_DIR}/lib/backend_bg.sh"
resolve_agent_paths "${REPO_ROOT}"

FRONTEND_PID="${FRONTEND_DIR}/.myrm-dev-frontend.pid"
FRONTEND_LOG="${FRONTEND_DIR}/.myrm-dev-frontend.log"
APP_URL="http://127.0.0.1:3000"
FRONTEND_PORT=3000
FRONTEND_COMPILE_WAIT_SEC=30

frontend_http_probe() {
  local max_time="${1:-8}"
  curl -sf --max-time "${max_time}" "${APP_URL}/" >/dev/null 2>&1
}

frontend_http_ok() {
  frontend_http_probe 8
}

frontend_port_listening() {
  lsof -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN -t >/dev/null 2>&1
}

wait_frontend_http() {
  local max="${1:-${FRONTEND_COMPILE_WAIT_SEC}}"
  for _ in $(seq 1 "${max}"); do
    if frontend_http_probe 2; then
      return 0
    fi
    sleep 1
  done
  return 1
}

warn_if_multiple_mcp() {
  local mcp_n
  mcp_n="$(pgrep -f 'npm exec chrome-devtools-mcp' 2>/dev/null | wc -l | tr -d ' ')"
  if [[ "${mcp_n}" -gt 1 ]]; then
    echo "⚠️  CHROME_E2E_WARN: Too many chrome-devtools-mcp processes (${mcp_n}) — close extra Agent tabs, then Cmd+Q Cursor" >&2
  fi
}

frontend_ready() {
  echo "✅ Frontend already running → ${APP_URL}"
  warn_if_multiple_mcp
  exit 0
}

if ! command -v bun >/dev/null 2>&1; then
  echo "ERROR: bun not found. Run: myrm setup" >&2
  exit 1
fi

if ! _start_backend_bg "${SERVER_DIR}"; then
  exit 1
fi
echo "✅ Backend http://127.0.0.1:8080"

if frontend_http_ok; then
  frontend_ready
fi

if frontend_port_listening; then
  echo "⏳ Frontend listening on :${FRONTEND_PORT} but HTTP not ready (cold compile?) — waiting up to ${FRONTEND_COMPILE_WAIT_SEC}s..."
  if wait_frontend_http "${FRONTEND_COMPILE_WAIT_SEC}"; then
    frontend_ready
  fi
  echo "⚠️  Frontend still not HTTP-ready after ${FRONTEND_COMPILE_WAIT_SEC}s — restarting..." >&2
fi

if [[ -f "${FRONTEND_PID}" ]]; then
  old_fp="$(cat "${FRONTEND_PID}")"
  if kill -0 "${old_fp}" 2>/dev/null; then
    kill "${old_fp}" 2>/dev/null || true
    sleep 1
  fi
  rm -f "${FRONTEND_PID}"
fi
rm -f "${FRONTEND_DIR}/.next/dev-server.lock"

cd "${FRONTEND_DIR}"
export MYRM_DEV_FORCE=1
nohup bun run dev >>"${FRONTEND_LOG}" 2>&1 &
echo $! >"${FRONTEND_PID}"

echo "🚀 Frontend starting (log: ${FRONTEND_LOG})"
for _ in $(seq 1 60); do
  if frontend_http_probe 8; then
    echo "✅ Open ${APP_URL}"
    echo "   Stop: myrm stop"
    warn_if_multiple_mcp
    exit 0
  fi
  sleep 1
done

echo "⚠️  Frontend slow to start; check ${FRONTEND_LOG}. Try ${APP_URL} shortly." >&2
warn_if_multiple_mcp
exit 0
