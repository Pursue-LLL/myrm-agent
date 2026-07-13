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
SOCK_FILE="${MYRM_SUPERVISOR_SOCKET:-${STATE_DIR}/supervisor.sock}"
START_LOCK_DIR="${STATE_DIR}/supervisor.start.lock"

export AGENT_ROOT SERVER_DIR FRONTEND_DIR MYRM_DEV_STATE_DIR="${STATE_DIR}"
export PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

_supervisor_alive() {
  [[ -f "${PID_FILE}" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' <"${PID_FILE}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null && [[ -S "${SOCK_FILE}" ]]
}

_supervisor_daemon_pids() {
  "${PY}" - "${PY}" "${STATE_DIR}" <<'PY'
import os
import shlex
import subprocess
import sys

target = os.path.abspath(sys.argv[1])
state_dir = os.path.abspath(sys.argv[2])
default_state_dir = os.path.abspath(os.path.expanduser("~/.local/state/myrm-dev"))
for raw in subprocess.check_output(["ps", "-axo", "pid=,command="], text=True).splitlines():
    fields = raw.strip().split(None, 1)
    if len(fields) != 2 or not fields[0].isdigit():
        continue
    try:
        args = shlex.split(fields[1])
    except ValueError:
        continue
    if len(args) < 3 or args[:3] != [target, "-m", "stack_supervisor.daemon"]:
        continue
    if "--state-dir" in args:
        index = args.index("--state-dir")
        if index + 1 >= len(args) or os.path.abspath(args[index + 1]) != state_dir:
            continue
    elif state_dir != default_state_dir:
        continue
    if args:
        print(fields[0])
PY
}

_stack_write_allowed() {
  local output
  if output="$(bash "${SCRIPT_DIR}/wave.sh" check-stack-write 2>&1)"; then
    return 0
  fi
  echo "${output}" >&2
  return 1
}

_wait_for_supervisor() {
  local i
  for i in $(seq 1 30); do
    if _supervisor_alive; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

_daemon_count() {
  _supervisor_daemon_pids | wc -l | tr -d '[:space:]'
}

cmd_start() {
  mkdir -p "${STATE_DIR}" "$(dirname "${SOCK_FILE}")"
  if ! mkdir "${START_LOCK_DIR}" 2>/dev/null; then
    if _wait_for_supervisor; then
      echo "SUPERVISOR_OK: started by concurrent launcher pid=$(tr -d '[:space:]' <"${PID_FILE}")"
      return 0
    fi
    echo "SUPERVISOR_FAIL: concurrent launcher did not produce a healthy daemon within 6s" >&2
    return 1
  fi

  local result=0
  if _supervisor_alive && [[ "$(_daemon_count)" == "1" ]]; then
    echo "SUPERVISOR_OK: already running pid=$(tr -d '[:space:]' <"${PID_FILE}")"
  elif [[ "$(_daemon_count)" != "0" ]]; then
    echo "SUPERVISOR_WARN: recovering unhealthy supervisor daemon" >&2
    if ! _stack_write_allowed; then
      echo "SUPERVISOR_BLOCKED: unhealthy daemon recovery requires an idle Wave" >&2
      result=3
    else
      cmd_stop
    fi
  fi

  if [[ "${result}" == "0" ]] && [[ ! -x "${PY}" ]]; then
    echo "SUPERVISOR_FAIL: missing server venv python at ${PY} — run: ./myrm setup" >&2
    result=1
  fi

  if [[ "${result}" == "0" ]] && ! _supervisor_alive; then
    nohup "${PY}" -m stack_supervisor.daemon --daemonize --state-dir "${STATE_DIR}" \
      >>"${STATE_DIR}/supervisor.log" 2>&1 &
  fi

  if [[ "${result}" == "0" ]] && _wait_for_supervisor; then
    if [[ "$(_daemon_count)" == "1" ]]; then
      echo "SUPERVISOR_OK: started pid=$(tr -d '[:space:]' <"${PID_FILE}")"
    else
      echo "SUPERVISOR_FAIL: expected one daemon, found $(_daemon_count)" >&2
      result=1
    fi
  elif [[ "${result}" == "0" ]]; then
    echo "SUPERVISOR_FAIL: daemon did not start within 6s — see ${STATE_DIR}/supervisor.log" >&2
    result=1
  fi

  rmdir "${START_LOCK_DIR}" 2>/dev/null || true
  return "${result}"
}

cmd_stop() {
  if _supervisor_alive; then
    "${PY}" -m stack_supervisor shutdown >/dev/null 2>&1 || true
  fi
  local pid=""
  if [[ -f "${PID_FILE}" ]]; then
    pid="$(tr -d '[:space:]' <"${PID_FILE}")"
  fi
  if [[ -n "${pid}" ]]; then
    kill -TERM "${pid}" 2>/dev/null || true
  fi
  local daemon_pid
  while IFS= read -r daemon_pid; do
    [[ -n "${daemon_pid}" ]] && kill -TERM "${daemon_pid}" 2>/dev/null || true
  done < <(_supervisor_daemon_pids)
  sleep 0.5
  while IFS= read -r daemon_pid; do
    [[ -n "${daemon_pid}" ]] && kill -0 "${daemon_pid}" 2>/dev/null && kill -9 "${daemon_pid}" 2>/dev/null || true
  done < <(_supervisor_daemon_pids)
  if [[ "$(_daemon_count)" == "0" ]]; then
    rm -f "${PID_FILE}" "${SOCK_FILE}" 2>/dev/null || true
  else
    echo "SUPERVISOR_WARN: daemon still alive; retaining pid/socket for diagnosis" >&2
  fi
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
    if [[ "${subcmd}" == "attach" ]]; then
      echo "SUPERVISOR_FAIL: attach requires a healthy supervisor — first Agent must run: ./myrm ready --chrome" >&2
      return 1
    fi
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
