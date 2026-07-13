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
START_LOCK_OWNER="${START_LOCK_DIR}/owner.pid"
START_LOCK_OWNED=0
START_WAIT_SEC="${MYRM_SUPERVISOR_START_WAIT_SEC:-90}"

if [[ ! "${START_WAIT_SEC}" =~ ^[1-9][0-9]*$ ]]; then
  echo "SUPERVISOR_FAIL: MYRM_SUPERVISOR_START_WAIT_SEC must be a positive integer" >&2
  exit 2
fi

export AGENT_ROOT SERVER_DIR FRONTEND_DIR MYRM_DEV_STATE_DIR="${STATE_DIR}"
export PYTHONPATH="${SCRIPT_DIR}${PYTHONPATH:+:${PYTHONPATH}}"

_supervisor_alive() {
  [[ -f "${PID_FILE}" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' <"${PID_FILE}")"
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null && [[ -S "${SOCK_FILE}" ]]
}

_supervisor_responsive() {
  _supervisor_alive || return 1
  "${PY}" - "${SOCK_FILE}" <<'PY'
import json
import socket
import sys

client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
client.settimeout(1.0)
try:
    client.connect(sys.argv[1])
    client.sendall(b'{"cmd":"ping","env":{}}\n')
    raw = b""
    while not raw.endswith(b"\n"):
        block = client.recv(65536)
        if not block:
            break
        raw += block
    payload = json.loads(raw)
    raise SystemExit(0 if payload.get("ok") else 1)
except (OSError, ValueError, socket.timeout):
    raise SystemExit(1)
finally:
    client.close()
PY
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
  for ((i = 0; i < START_WAIT_SEC * 5; i++)); do
    if _supervisor_responsive; then
      return 0
    fi
    sleep 0.2
  done
  return 1
}

_daemon_count() {
  _supervisor_daemon_pids | wc -l | tr -d '[:space:]'
}

_release_start_lock() {
  if [[ "${START_LOCK_OWNED}" == "1" ]]; then
    rm -f "${START_LOCK_OWNER}" 2>/dev/null || true
    rmdir "${START_LOCK_DIR}" 2>/dev/null || true
    START_LOCK_OWNED=0
  fi
}

_acquire_start_lock() {
  if mkdir "${START_LOCK_DIR}" 2>/dev/null; then
    echo "$$" >"${START_LOCK_OWNER}"
    START_LOCK_OWNED=1
    return 0
  fi
  local owner=""
  if [[ -f "${START_LOCK_OWNER}" ]]; then
    owner="$(tr -d '[:space:]' <"${START_LOCK_OWNER}")"
  fi
  if [[ -n "${owner}" ]] && kill -0 "${owner}" 2>/dev/null; then
    return 1
  fi
  rm -f "${START_LOCK_OWNER}" 2>/dev/null || true
  rmdir "${START_LOCK_DIR}" 2>/dev/null || return 1
  if mkdir "${START_LOCK_DIR}" 2>/dev/null; then
    echo "$$" >"${START_LOCK_OWNER}"
    START_LOCK_OWNED=1
    return 0
  fi
  return 1
}

cmd_start() {
  mkdir -p "${STATE_DIR}" "$(dirname "${SOCK_FILE}")"
  if ! _acquire_start_lock; then
    if _wait_for_supervisor; then
      echo "SUPERVISOR_OK: started by concurrent launcher pid=$(tr -d '[:space:]' <"${PID_FILE}")"
      return 0
    fi
    echo "SUPERVISOR_FAIL: concurrent launcher did not produce a healthy daemon within ${START_WAIT_SEC}s" >&2
    return 1
  fi

  local result=0
  if _supervisor_responsive && [[ "$(_daemon_count)" == "1" ]]; then
    echo "SUPERVISOR_OK: already running pid=$(tr -d '[:space:]' <"${PID_FILE}")"
    _release_start_lock
    return 0
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

  if [[ "${result}" == "0" ]] && ! _supervisor_responsive; then
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
    echo "SUPERVISOR_FAIL: daemon did not start within ${START_WAIT_SEC}s — see ${STATE_DIR}/supervisor.log" >&2
    result=1
  fi

  _release_start_lock
  return "${result}"
}

cmd_stop() {
  if _supervisor_responsive; then
    "${PY}" -m stack_supervisor shutdown >/dev/null 2>&1 || true
  fi
  local pid=""
  if [[ -f "${PID_FILE}" ]]; then
    pid="$(tr -d '[:space:]' <"${PID_FILE}")"
  fi
  local daemon_pid daemon_pids remaining=0
  daemon_pids="$(_supervisor_daemon_pids)"
  if [[ -n "${pid}" ]]; then
    kill -TERM "${pid}" 2>/dev/null || true
  fi
  while IFS= read -r daemon_pid; do
    [[ -n "${daemon_pid}" ]] && kill -TERM "${daemon_pid}" 2>/dev/null || true
  done <<<"${daemon_pids}"
  local attempt
  for attempt in $(seq 1 20); do
    remaining=0
    while IFS= read -r daemon_pid; do
      if [[ -n "${daemon_pid}" ]] && kill -0 "${daemon_pid}" 2>/dev/null; then
        remaining=1
      fi
    done <<<"${daemon_pids}"
    [[ "${remaining}" == "0" ]] && break
    sleep 0.1
  done
  while IFS= read -r daemon_pid; do
    [[ -n "${daemon_pid}" ]] && kill -0 "${daemon_pid}" 2>/dev/null && kill -9 "${daemon_pid}" 2>/dev/null || true
  done <<<"${daemon_pids}"
  sleep 0.1
  remaining=0
  while IFS= read -r daemon_pid; do
    if [[ -n "${daemon_pid}" ]] && kill -0 "${daemon_pid}" 2>/dev/null; then
      remaining=1
    fi
  done <<<"${daemon_pids}"
  if [[ "${remaining}" == "0" ]]; then
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
  trap _release_start_lock EXIT INT TERM
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
