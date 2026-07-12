#!/usr/bin/env bash
# Stack supervisor launcher — single writer for dev-stack ensure/reset.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
resolve_agent_paths "${REPO_ROOT}"

STATE_DIR="${MYRM_DEV_STATE_DIR:-${HOME}/.local/state/myrm-dev}"
PY="${SERVER_DIR}/.venv/bin/python"
PID_FILE="${STATE_DIR}/supervisor.pid"
SOCK_FILE="${STATE_DIR}/supervisor.sock"

export AGENT_ROOT SERVER_DIR FRONTEND_DIR MYRM_DEV_STATE_DIR="${STATE_DIR}"
export PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

_supervisor_alive() {
  [[ -f "${PID_FILE}" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' <"${PID_FILE}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null && [[ -S "${SOCK_FILE}" ]]
}

cmd_start() {
  mkdir -p "${STATE_DIR}"
  if _supervisor_alive; then
    echo "SUPERVISOR_OK: already running pid=$(tr -d '[:space:]' <"${PID_FILE}")"
    return 0
  fi
  if [[ ! -x "${PY}" ]]; then
    echo "SUPERVISOR_FAIL: missing server venv python at ${PY} — run: ./myrm setup" >&2
    return 1
  fi
  rm -f "${SOCK_FILE}" 2>/dev/null || true
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup "${PY}" -m stack_supervisor.daemon --daemonize >>"${STATE_DIR}/supervisor.log" 2>&1 &
  else
    nohup "${PY}" -m stack_supervisor.daemon --daemonize >>"${STATE_DIR}/supervisor.log" 2>&1 &
  fi
  local i
  for i in $(seq 1 30); do
    if _supervisor_alive; then
      echo "SUPERVISOR_OK: started pid=$(tr -d '[:space:]' <"${PID_FILE}")"
      return 0
    fi
    sleep 0.2
  done
  echo "SUPERVISOR_FAIL: daemon did not start within 6s — see ${STATE_DIR}/supervisor.log" >&2
  return 1
}

cmd_stop() {
  if ! _supervisor_alive; then
    rm -f "${PID_FILE}" "${SOCK_FILE}" 2>/dev/null || true
    echo "SUPERVISOR_OK: not running"
    return 0
  fi
  "${PY}" -m stack_supervisor shutdown >/dev/null 2>&1 || true
  local pid=""
  if [[ -f "${PID_FILE}" ]]; then
    pid="$(tr -d '[:space:]' <"${PID_FILE}")"
  fi
  if [[ -n "${pid}" ]]; then
    kill -TERM "${pid}" 2>/dev/null || true
    sleep 0.5
    kill -0 "${pid}" 2>/dev/null && kill -9 "${pid}" 2>/dev/null || true
  fi
  rm -f "${PID_FILE}" "${SOCK_FILE}" 2>/dev/null || true
  echo "SUPERVISOR_OK: stopped"
}

cmd_rpc() {
  local subcmd="${1:-}"
  [[ -n "${subcmd}" ]] || {
    echo "Usage: stack-supervisor.sh rpc <ensure|attach|reset|status|ping|shutdown>" >&2
    return 1
  }
  if [[ ! -x "${PY}" ]]; then
    echo "SUPERVISOR_FAIL: missing server venv python" >&2
    return 1
  fi
  if ! _supervisor_alive; then
    cmd_start || return 1
  fi
  "${PY}" -m stack_supervisor "${subcmd}"
}

usage() {
  echo "Usage: stack-supervisor.sh start|stop|rpc <cmd>" >&2
}

main() {
  local cmd="${1:-}"
  case "${cmd}" in
    start) cmd_start ;;
    stop) cmd_stop ;;
    rpc) shift; cmd_rpc "$@" ;;
    ""|-h|--help) usage; exit 1 ;;
    *)
      echo "Unknown command: ${cmd}" >&2
      usage
      exit 1
      ;;
  esac
}

main "$@"
