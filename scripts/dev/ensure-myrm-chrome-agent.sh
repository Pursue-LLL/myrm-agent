#!/usr/bin/env bash
# Launch or verify Myrm Agent Chrome (pipe-proxy :9410, no macOS focus theft).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AGENT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=lib/dev_state_paths.sh
source "${AGENT_ROOT}/scripts/dev/lib/dev_state_paths.sh"
export_spawn_home

MYRM_CHROME_AGENT_PORT="${MYRM_CHROME_AGENT_PORT:-9410}"
MYRM_CHROME_AGENT_DATA_DIR="${MYRM_CHROME_AGENT_DATA_DIR:-${HOME}/Library/Application Support/Myrm/ChromeAgent}"
MYRM_CHROME_AGENT_CHROME_PATH="${MYRM_CHROME_AGENT_CHROME_PATH:-${SCRIPT_DIR}/chrome-agent/chrome-arm64-launcher.sh}"
CHROME_LAUNCHER="$(cd "$(dirname "${MYRM_CHROME_AGENT_CHROME_PATH}")" && pwd)/$(basename "${MYRM_CHROME_AGENT_CHROME_PATH}")"
PROXY_DIR="${SCRIPT_DIR}/chrome-agent"
PID_FILE="${MYRM_CHROME_AGENT_PID_FILE:-$(dev_state_dir)/chrome-agent-proxy.pid}"
LOG_FILE="${MYRM_CHROME_AGENT_LOG_FILE:-$(dev_state_dir)/chrome-agent-proxy.log}"

fail() {
  echo "MYRM_CHROME_AGENT_FAIL: $*" >&2
  exit 1
}

ok() {
  echo "MYRM_CHROME_AGENT_OK: $*"
}

_chrome_agent_healthy() {
  curl -sf --max-time 3 "http://127.0.0.1:${MYRM_CHROME_AGENT_PORT}/proxy/status" \
    | python3 -c 'import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get("chromeRunning") else 1)' \
    2>/dev/null
}

_read_pid() {
  [[ -f "${PID_FILE}" ]] || return 1
  local raw
  raw="$(tr -d '[:space:]' <"${PID_FILE}")"
  [[ "${raw}" =~ ^[0-9]+$ ]] || return 1
  echo "${raw}"
}

_stale_port_pid() {
  lsof -tiTCP:"${MYRM_CHROME_AGENT_PORT}" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

if _chrome_agent_healthy; then
  live_pid="$(_stale_port_pid || true)"
  if [[ -n "${live_pid}" ]]; then
    echo "${live_pid}" >"${PID_FILE}"
  fi
  ok "already running port=${MYRM_CHROME_AGENT_PORT} profile=${MYRM_CHROME_AGENT_DATA_DIR}"
  exit 0
fi

stale_port_pid="$(_stale_port_pid)"
if [[ -n "${stale_port_pid}" ]]; then
  echo "MYRM_CHROME_AGENT_HEAL: freeing stale listener pid=${stale_port_pid} on :${MYRM_CHROME_AGENT_PORT}" >&2
  kill "${stale_port_pid}" 2>/dev/null || true
  sleep 1
fi

if [[ -f "${PID_FILE}" ]]; then
  stale_pid="$(_read_pid || true)"
  if [[ -n "${stale_pid:-}" ]] && kill -0 "${stale_pid}" 2>/dev/null; then
    echo "MYRM_CHROME_AGENT_WAIT: proxy pid=${stale_pid} starting..." >&2
    for _ in $(seq 1 30); do
      if _chrome_agent_healthy; then
        ok "became healthy port=${MYRM_CHROME_AGENT_PORT}"
        exit 0
      fi
      sleep 1
    done
    fail "proxy pid=${stale_pid} alive but /proxy/status unhealthy — see ${LOG_FILE}"
  fi
  rm -f "${PID_FILE}"
fi

if lsof -iTCP:"${MYRM_CHROME_AGENT_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  fail "Port ${MYRM_CHROME_AGENT_PORT} in use by non-Myrm process — free the port or set MYRM_CHROME_AGENT_PORT"
fi

[[ -x "${CHROME_LAUNCHER}" ]] || fail "missing Chrome launcher ${CHROME_LAUNCHER}"
if [[ ! -d "${PROXY_DIR}/node_modules/ws" ]]; then
  echo "MYRM_CHROME_AGENT_NPM: installing ws in ${PROXY_DIR}" >&2
  (cd "${PROXY_DIR}" && npm install --ignore-scripts) || fail "npm install failed in ${PROXY_DIR}"
fi

NODE_BIN="${MYRM_NODE_BIN:-}"
if [[ -z "${NODE_BIN}" ]]; then
  NODE_BIN="$(command -v node || true)"
fi
[[ -n "${NODE_BIN}" && -x "${NODE_BIN}" ]] || fail "node not found — set MYRM_NODE_BIN"

mkdir -p "$(dev_state_dir)" "${MYRM_CHROME_AGENT_DATA_DIR}"

echo "MYRM_CHROME_AGENT_START: pipe-proxy port=${MYRM_CHROME_AGENT_PORT}" >&2
nohup "${NODE_BIN}" "${PROXY_DIR}/pipe-cdp-proxy.mjs" \
  --port "${MYRM_CHROME_AGENT_PORT}" \
  --chrome-path "${CHROME_LAUNCHER}" \
  --user-data-dir "${MYRM_CHROME_AGENT_DATA_DIR}" \
  >>"${LOG_FILE}" 2>&1 </dev/null &
proxy_pid=$!
echo "${proxy_pid}" >"${PID_FILE}"
disown "${proxy_pid}" 2>/dev/null || true

for _ in $(seq 1 60); do
  if _chrome_agent_healthy; then
    ok "started port=${MYRM_CHROME_AGENT_PORT} profile=${MYRM_CHROME_AGENT_DATA_DIR} log=${LOG_FILE}"
    exit 0
  fi
  sleep 1
done

fail "timeout waiting for proxy — see ${LOG_FILE}"
