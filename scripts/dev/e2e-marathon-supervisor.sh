#!/usr/bin/env bash
# Marathon supervisor launcher — exclusive serial chrome_e2e with checkpoint ledger.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
resolve_agent_paths "${REPO_ROOT}"
# shellcheck source=lib/dev_state_paths.sh
source "${SCRIPT_DIR}/lib/dev_state_paths.sh"

STATE_DIR="$(dev_state_dir)"
PY="${SERVER_DIR}/.venv/bin/python"
PID_FILE="${STATE_DIR}/marathon.pid"
SOCK_FILE="${MYRM_MARATHON_SOCKET:-${STATE_DIR}/marathon.sock}"
export AGENT_ROOT SERVER_DIR FRONTEND_DIR MYRM_DEV_STATE_DIR="${STATE_DIR}"
export PYTHONPATH="${SCRIPT_DIR}/lib${PYTHONPATH:+:${PYTHONPATH}}"

_supervisor_alive() {
  [[ -f "${PID_FILE}" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' <"${PID_FILE}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null && [[ -S "${SOCK_FILE}" ]]
}

cmd_start() {
  mkdir -p "${STATE_DIR}" "$(dirname "${SOCK_FILE}")"
  if _supervisor_alive; then
    echo "MARATHON_OK: already running pid=$(tr -d '[:space:]' <"${PID_FILE}")"
    return 0
  fi
  if [[ ! -x "${PY}" ]]; then
    echo "MARATHON_FAIL: missing venv python at ${PY}" >&2
    return 1
  fi
  nohup "${PY}" -m e2e_marathon.daemon --daemonize \
    >>"${STATE_DIR}/marathon-supervisor.log" 2>&1 &
  sleep 1
  if _supervisor_alive; then
    echo "MARATHON_OK: started pid=$(tr -d '[:space:]' <"${PID_FILE}")"
    return 0
  fi
  echo "MARATHON_FAIL: daemon did not start — see ${STATE_DIR}/marathon-supervisor.log" >&2
  return 1
}

cmd_stop() {
  if _supervisor_alive; then
    "${PY}" -m e2e_marathon.client shutdown >/dev/null 2>&1 || true
    local pid
    pid="$(tr -d '[:space:]' <"${PID_FILE}")"
    kill -TERM "${pid}" 2>/dev/null || true
    sleep 0.5
  fi
  rm -f "${PID_FILE}" "${SOCK_FILE}" "${STATE_DIR}/marathon-lock.json" 2>/dev/null || true
  echo "MARATHON_OK: stopped"
}

cmd_rpc() {
  local subcmd="${1:-status}"
  if [[ ! -x "${PY}" ]]; then
    echo "MARATHON_FAIL: missing venv python" >&2
    return 1
  fi
  if ! _supervisor_alive; then
    if [[ "${subcmd}" == "status" ]]; then
      echo '{"running":false,"ledger":null}'
      return 0
    fi
    cmd_start || return 1
  fi
  "${PY}" -m e2e_marathon.client "${subcmd}"
}

usage() {
  echo "Usage: e2e-marathon-supervisor.sh start|stop|rpc <start|status|shutdown|ping>" >&2
}

main() {
  local cmd="${1:-}"
  case "${cmd}" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    rpc) shift; cmd_rpc "${1:-status}" ;;
    ""|-h|--help) usage; exit 1 ;;
    *)
      echo "Unknown command: ${cmd}" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
