#!/usr/bin/env bash
# Launch or verify ChromeAgent pipe-proxy (:9410, no macOS focus theft).
# Preferred path is the LaunchAgent daemon (./myrm ready --chrome-agent --daemon);
# this script health-checks first and only falls back to a nohup proxy when no
# daemon is installed. All runtime paths resolve from the machine-level
# `current` symlink, so the repo can be moved or deleted afterwards.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=chrome-agent/lib-chrome-agent.sh
source "${SCRIPT_DIR}/chrome-agent/lib-chrome-agent.sh"

MYRM_CHROME_AGENT_PORT="${MYRM_CHROME_AGENT_PORT:-${CHROME_AGENT_DEFAULT_PORT}}"
PID_FILE="${MYRM_CHROME_AGENT_PID_FILE:-$(real_user_home)/.local/state/myrm-dev/chrome-agent-proxy.pid}"
LOG_FILE="$(chrome_agent_log_file)"
CURRENT_DIR="$(chrome_agent_current_link)"

fail() {
  echo "MYRM_CHROME_AGENT_FAIL: $*" >&2
  exit 1
}

ok() {
  echo "MYRM_CHROME_AGENT_OK: $*"
}

_stale_port_pid() {
  lsof -tiTCP:"${MYRM_CHROME_AGENT_PORT}" -sTCP:LISTEN 2>/dev/null | head -1 || true
}

_read_pid() {
  [[ -f "${PID_FILE}" ]] || return 1
  local raw
  raw="$(tr -d '[:space:]' <"${PID_FILE}")"
  [[ "${raw}" =~ ^[0-9]+$ ]] || return 1
  echo "${raw}"
}

if chrome_agent_health; then
  live_pid="$(_stale_port_pid || true)"
  [[ -n "${live_pid}" ]] && echo "${live_pid}" >"${PID_FILE}"
  ok "already running port=${MYRM_CHROME_AGENT_PORT} profile=$(chrome_agent_data_dir)"
  exit 0
fi

# Machine-level bundle must exist before anything else; auto-install on first run.
if [[ ! -L "${CURRENT_DIR}" ]] || [[ ! -f "${CURRENT_DIR}/pipe-cdp-proxy.mjs" ]]; then
  echo "MYRM_CHROME_AGENT_AUTO_INSTALL: installing machine-level bundle..." >&2
  bash "${SCRIPT_DIR}/chrome-agent/myrm-chrome-agent.sh" install \
    || fail "machine-level install failed — run ./myrm ready --chrome-agent --daemon"
fi

if chrome_agent_launchagent_loaded; then
  echo "MYRM_CHROME_AGENT_DAEMON: restarting LaunchAgent ${CHROME_AGENT_LABEL}..." >&2
  chrome_agent_launchagent_start
  chrome_agent_wait_health \
    && ok "daemon healthy port=${MYRM_CHROME_AGENT_PORT}" && exit 0 \
    || fail "daemon unhealthy — see ${LOG_FILE}"
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
    chrome_agent_wait_health \
      && ok "became healthy port=${MYRM_CHROME_AGENT_PORT}" && exit 0
    fail "proxy pid=${stale_pid} alive but /proxy/status unhealthy — see ${LOG_FILE}"
  fi
  rm -f "${PID_FILE}"
fi

if lsof -iTCP:"${MYRM_CHROME_AGENT_PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  fail "Port ${MYRM_CHROME_AGENT_PORT} in use by non-Myrm process — free the port or set MYRM_CHROME_AGENT_PORT"
fi

NODE_BIN="${MYRM_NODE_BIN:-$(command -v node || true)}"
[[ -n "${NODE_BIN}" && -x "${NODE_BIN}" ]] || fail "node not found — set MYRM_NODE_BIN"

mkdir -p "$(dirname "${PID_FILE}")" "$(dirname "${LOG_FILE}")" "$(chrome_agent_data_dir)"

echo "MYRM_CHROME_AGENT_START: pipe-proxy port=${MYRM_CHROME_AGENT_PORT} (nohup fallback)" >&2
nohup "${NODE_BIN}" "${CURRENT_DIR}/pipe-cdp-proxy.mjs" \
  --port "${MYRM_CHROME_AGENT_PORT}" \
  --chrome-path "${CURRENT_DIR}/chrome-arm64-launcher.sh" \
  --user-data-dir "$(chrome_agent_data_dir)" \
  >>"${LOG_FILE}" 2>&1 </dev/null &
proxy_pid=$!
echo "${proxy_pid}" >"${PID_FILE}"
disown "${proxy_pid}" 2>/dev/null || true

chrome_agent_wait_health \
  && ok "started port=${MYRM_CHROME_AGENT_PORT} profile=$(chrome_agent_data_dir) log=${LOG_FILE}" \
  || fail "timeout waiting for proxy — see ${LOG_FILE}"
