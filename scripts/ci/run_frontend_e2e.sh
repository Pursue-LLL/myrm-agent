#!/usr/bin/env bash
# Playwright UI E2E: backend :8080 + frontend :3000 + tests/e2e/*.spec.ts
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SERVER_DIR="${ROOT}/myrm-agent-server"
FRONTEND_DIR="${ROOT}/myrm-agent-frontend"
WS_DIR="$(mktemp -d)"
BACKEND_PID=""
FRONTEND_PID=""

_cleanup() {
  if [[ -n "${FRONTEND_PID}" ]]; then
    kill "${FRONTEND_PID}" 2>/dev/null || true
  fi
  if [[ -n "${BACKEND_PID}" ]]; then
    kill "${BACKEND_PID}" 2>/dev/null || true
  fi
  rm -rf "${WS_DIR}"
}
trap _cleanup EXIT

_wait_http() {
  local url="$1"
  local label="$2"
  local retries="${3:-60}"
  for _ in $(seq 1 "${retries}"); do
    if curl -sf --max-time 2 "${url}" >/dev/null; then
      echo "==> ${label} ready: ${url}"
      return 0
    fi
    sleep 2
  done
  echo "ERROR: ${label} not ready at ${url}" >&2
  return 1
}

echo "==> [1/4] Install backend dependencies"
SERVER_ROOT="${SERVER_DIR}"
# shellcheck source=../../myrm-agent-server/scripts/ci/lib_harness_deps.sh
source "${SERVER_DIR}/scripts/ci/lib_harness_deps.sh"
myrm_ci_install_server_deps --reuse-venv

echo "==> [2/4] Start backend on :8080"
cd "${SERVER_DIR}"
export MYRM_DATA_DIR="${WS_DIR}"
export DEPLOY_MODE=local
export SKIP_HEALTH_CHECK=true
uv run run.py --port 8080 >"${WS_DIR}/backend.log" 2>&1 &
BACKEND_PID=$!
_wait_http "http://127.0.0.1:8080/api/v1/health" "backend"

echo "==> [3/4] Build and start frontend on :3000"
cd "${FRONTEND_DIR}"
bun install --frozen-lockfile
bunx playwright install chromium --with-deps
NEXT_PUBLIC_DEPLOY_MODE=local bun run build
PORT=3000 HOSTNAME=127.0.0.1 bun run start >"${WS_DIR}/frontend.log" 2>&1 &
FRONTEND_PID=$!
_wait_http "http://127.0.0.1:3000/" "frontend" 90

echo "==> [4/4] Run Playwright E2E"
PLAYWRIGHT_SKIP_WEBSERVER=1 \
PLAYWRIGHT_BASE_URL=http://127.0.0.1:3000 \
PLAYWRIGHT_API_BASE=http://127.0.0.1:8080 \
PLAYWRIGHT_RUN_WEBUI_E2E=1 \
PLAYWRIGHT_RUN_INSTINCT_INBOX_E2E=1 \
PLAYWRIGHT_RUN_MCP_SCAN_E2E=1 \
  bunx playwright test --reporter=line

echo "==> Frontend Playwright E2E passed."
