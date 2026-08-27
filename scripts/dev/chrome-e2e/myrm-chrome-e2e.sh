#!/usr/bin/env bash
# Myrm E2E Chrome CLI — manage dedicated test browser and orchestrator daemons.
#
# Subcommands:
#   status           Read-only report of port, pid, profile, health and active tabs.
#   stop             Gracefully stop browser-orchestrator, cdmcp-mux and ChromeE2E.
#   start            Start or ensure dedicated E2E Chrome (supports --foreground).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=runtime.sh
source "${SCRIPT_DIR}/runtime.sh"
# shellcheck source=lifecycle.sh
source "${SCRIPT_DIR}/lifecycle.sh"

REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"

fail() {
  echo "MYRM_CHROME_E2E_FAIL: $*" >&2
  exit 1
}

ok() {
  echo "MYRM_CHROME_E2E_OK: $*"
}

cmd_status() {
  local port="${MYRM_CHROME_E2E_PORT:-9333}"
  local data_dir="${MYRM_CHROME_E2E_DATA_DIR}"
  local healthy="unhealthy"
  local pid=""
  local tab_count="0"

  pid="$(chrome_e2e_owner_pid)"
  if chrome_e2e_cdp_healthy; then
    healthy="healthy"
    local list_json
    list_json="$(curl -sf --max-time 2 "http://127.0.0.1:${port}/json/list" 2>/dev/null || echo '[]')"
    tab_count="$(python3 -c "import json, sys; data=json.loads(sys.argv[1]); print(len(data))" "${list_json}" 2>/dev/null || echo '0')"
  fi

  echo "CHROME_E2E_STATUS: port=${port} health=${healthy} pid=${pid:-'none'}"
  echo "CHROME_E2E_STATUS: profile=${data_dir}"
  echo "CHROME_E2E_STATUS: active_tabs=${tab_count}"
}

cmd_stop() {
  local port="${MYRM_CHROME_E2E_PORT:-9333}"
  local orch_main="${REPO_ROOT}/scripts/dev/browser-orchestrator/dist/bin/main.js"

  # 1. Stop browser-orchestrator daemon if running
  if [[ -f "${orch_main}" ]] && command -v node >/dev/null 2>&1; then
    node "${orch_main}" stop >/dev/null 2>&1 || true
  fi
  pkill -f "browser-orchestrator" >/dev/null 2>&1 || true

  # 2. Stop cdmcp-mux-autoconnect daemon
  pkill -f "cdmcp-mux-autoconnect" >/dev/null 2>&1 || true

  # 3. Terminate ChromeE2E listener on port :9333
  for pid in $(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true); do
    kill -TERM "${pid}" 2>/dev/null || true
  done
  sleep 0.2
  for pid in $(lsof -tiTCP:"${port}" -sTCP:LISTEN 2>/dev/null || true); do
    kill -9 "${pid}" 2>/dev/null || true
  done

  # 4. Fallback kill by profile identifier
  for pid in $(ps aux | grep -i "ChromeE2E" | grep -v grep | awk '{print $2}'); do
    kill -9 "${pid}" 2>/dev/null || true
  done

  ok "stopped E2E Chrome and orchestrator daemons (port :${port} freed)"
}

cmd_start() {
  local ensure_script="${SCRIPT_DIR}/../ensure-myrm-chrome-e2e.sh"
  if [[ ! -f "${ensure_script}" ]]; then
    fail "ensure script not found at ${ensure_script}"
  fi

  while [[ $# -gt 0 ]]; do
    case "$1" in
      --foreground|-f)
        export MYRM_CHROME_E2E_FOREGROUND=1
        shift
        ;;
      *)
        shift
        ;;
    esac
  done

  exec bash "${ensure_script}"
}

case "${1:-status}" in
  status) cmd_status ;;
  stop) cmd_stop ;;
  start)
    shift || true
    cmd_start "$@"
    ;;
  *)
    echo "Usage: myrm-chrome-e2e.sh {status|stop|start [--foreground]}" >&2
    exit 1
    ;;
esac
