#!/usr/bin/env bash
# Dev stack supervisor — single lifecycle SSOT for local :8080/:3000.
# Usage: dev-stack.sh ensure|attach|reset|status
#   ensure  — mkdir atomic lock + start stack if unhealthy (idempotent)
#   attach  — wait for healthy stack, zero start/kill side effects
#   reset   — stop backend + frontend (only legal kill entry)
#   status  — JSON-ish health snapshot
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
# shellcheck source=../lib/resolve_agent_root.sh
source "${REPO_ROOT}/scripts/lib/resolve_agent_root.sh"
# shellcheck source=lib/backend_bg.sh
source "${SCRIPT_DIR}/lib/backend_bg.sh"
# shellcheck source=lib/frontend-warmup.sh
source "${SCRIPT_DIR}/lib/frontend-warmup.sh"
# shellcheck source=lib/stack-epoch.sh
source "${SCRIPT_DIR}/lib/stack-epoch.sh"
resolve_agent_paths "${REPO_ROOT}"

STATE_DIR="${MYRM_DEV_STATE_DIR:-${HOME}/.local/state/myrm-dev}"

FRONTEND_PID="${FRONTEND_DIR}/.myrm-dev-frontend.pid"
FRONTEND_LOG="${FRONTEND_DIR}/.myrm-dev-frontend.log"
FRONTEND_LOCK="${FRONTEND_DIR}/.next/dev-server.lock"
APP_URL="http://127.0.0.1:3000"
API_HEALTH="http://127.0.0.1:8080/api/v1/health"
FRONTEND_PORT=3000

ATTACH_WAIT_SEC="${MYRM_STACK_ATTACH_WAIT_SEC:-120}"
ENSURE_FRONTEND_WAIT_SEC="${MYRM_STACK_FRONTEND_WAIT_SEC:-120}"
API_E2E_LOCK_WAIT_SEC="${MYRM_API_E2E_LOCK_WAIT_SEC:-600}"

mkdir -p "${STATE_DIR}"

_lock_dir="${STATE_DIR}/ensure.lock.d"
_api_lock_dir="${STATE_DIR}/api-e2e.lock.d"

_acquire_dir_lock() {
  local lockdir="$1"
  local wait_sec="$2"
  local i

  if [[ -d "${lockdir}" ]]; then
    local owner=""
    if [[ -f "${lockdir}/pid" ]]; then
      owner="$(tr -d '[:space:]' <"${lockdir}/pid")"
    fi
    if [[ -z "${owner}" ]] || ! kill -0 "${owner}" 2>/dev/null; then
      echo "STACK_WARN: reclaiming stale lock ${lockdir}" >&2
      _release_dir_lock "${lockdir}"
    fi
  fi

  for i in $(seq 1 "${wait_sec}"); do
    if mkdir "${lockdir}" 2>/dev/null; then
      echo "$$" >"${lockdir}/pid"
      return 0
    fi
    sleep 1
  done
  return 1
}

_release_dir_lock() {
  local lockdir="$1"
  rm -f "${lockdir}/pid" 2>/dev/null || true
  rmdir "${lockdir}" 2>/dev/null || true
}

_http_ok() {
  local url="$1"
  local max_time="${2:-8}"
  curl -sf --max-time "${max_time}" "${url}" >/dev/null 2>&1
}

_api_healthy() {
  _http_ok "${API_HEALTH}" "${1:-5}"
}

_frontend_healthy() {
  _http_ok "${APP_URL}/" "${1:-8}"
}

_stack_healthy() {
  _api_healthy 5 && _frontend_healthy 8
}

_stack_warm() {
  _api_healthy 5 && [[ "$(_frontend_compile_hot_status)" == "yes" ]]
}

_wait_stack_health() {
  local max="${1:-${ATTACH_WAIT_SEC}}"
  local i
  for i in $(seq 1 "${max}"); do
    if _stack_healthy; then
      return 0
    fi
    sleep 1
  done
  return 1
}

_wait_stack_warm() {
  local max="${1:-${ATTACH_WAIT_SEC}}"
  local i
  for i in $(seq 1 "${max}"); do
    if _stack_warm; then
      return 0
    fi
    sleep 1
  done
  return 1
}

_lock_supervisor_alive() {
  [[ -f "${FRONTEND_LOCK}" ]] || return 1
  local pid
  pid="$(python3 -c "
import json, sys
from pathlib import Path
p = Path('${FRONTEND_LOCK}')
if not p.is_file():
    sys.exit(1)
data = json.loads(p.read_text())
pid = data.get('pid')
if not isinstance(pid, int):
    sys.exit(1)
print(pid)
" 2>/dev/null)" || return 1
  [[ -n "${pid}" ]] && kill -0 "${pid}" 2>/dev/null
}

_frontend_port_listening() {
  lsof -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN -t >/dev/null 2>&1
}

_sync_frontend_pid_from_lock() {
  if [[ ! -f "${FRONTEND_LOCK}" ]]; then
    return 0
  fi
  local pid
  pid="$(python3 -c "
import json
from pathlib import Path
p = Path('${FRONTEND_LOCK}')
data = json.loads(p.read_text())
print(data.get('pid', ''))
" 2>/dev/null)" || return 0
  if [[ -n "${pid}" ]] && [[ "${pid}" =~ ^[0-9]+$ ]]; then
    echo "${pid}" >"${FRONTEND_PID}"
  fi
}

_repair_orphan_frontend() {
  if _frontend_healthy; then
    _sync_frontend_pid_from_lock
    return 0
  fi
  if ! _frontend_port_listening; then
    return 0
  fi
  if _lock_supervisor_alive; then
    return 0
  fi
  echo "STACK_WARN: orphan :${FRONTEND_PORT} listener without dev-server.lock — clearing" >&2
  local pids
  pids="$(lsof -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ')"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 1
  fi
  rm -f "${FRONTEND_PID}" "${FRONTEND_LOCK}"
}

_start_frontend_supervisor() {
  if _frontend_healthy; then
    _sync_frontend_pid_from_lock
    echo "STACK_OK: frontend already healthy → ${APP_URL}"
    return 0
  fi

  if _frontend_port_listening && _lock_supervisor_alive; then
    echo "STACK_WAIT: frontend compiling — up to ${ENSURE_FRONTEND_WAIT_SEC}s..."
    if _wait_stack_health "${ENSURE_FRONTEND_WAIT_SEC}"; then
      _sync_frontend_pid_from_lock
      echo "STACK_OK: frontend ready after compile wait"
      return 0
    fi
    echo "STACK_WARN: frontend still not HTTP-ready after compile wait — check ${FRONTEND_LOG}" >&2
    return 1
  fi

  _repair_orphan_frontend

  if ! command -v bun >/dev/null 2>&1; then
    echo "STACK_FAIL: bun not found — run: myrm setup" >&2
    return 1
  fi

  cd "${FRONTEND_DIR}"
  bash "${SCRIPT_DIR}/ensure-next-native-swc.sh"
  _frontend_clear_warmth
  nohup bun run dev >>"${FRONTEND_LOG}" 2>&1 &
  echo $! >"${FRONTEND_PID}"
  echo "STACK_START: frontend supervisor pid $(cat "${FRONTEND_PID}")"

  local i
  for i in $(seq 1 "${ENSURE_FRONTEND_WAIT_SEC}"); do
    if _frontend_healthy; then
      _sync_frontend_pid_from_lock
      echo "STACK_OK: frontend → ${APP_URL}"
      return 0
    fi
    sleep 1
  done
  echo "STACK_WARN: frontend slow to start — check ${FRONTEND_LOG}" >&2
  return 1
}

_ensure_backend() {
  if ! _start_backend_bg "${SERVER_DIR}"; then
    echo "STACK_FAIL: backend start failed" >&2
    return 1
  fi
  if _api_healthy 10; then
    echo "STACK_OK: backend → http://127.0.0.1:8080"
    return 0
  fi
  echo "STACK_FAIL: backend not healthy after start" >&2
  return 1
}

cmd_attach() {
  if _wait_stack_warm "${ATTACH_WAIT_SEC}"; then
    echo "STACK_ATTACH_OK api=:8080 ui=:3000 shell_hot=yes"
    exit 0
  fi
  echo "STACK_ATTACH_TIMEOUT: stack not shell_hot within ${ATTACH_WAIT_SEC}s — run: ./myrm ready" >&2
  exit 1
}

cmd_ensure() {
  if ! _acquire_dir_lock "${_lock_dir}" "${ATTACH_WAIT_SEC}"; then
    echo "STACK_FAIL: could not acquire stack ensure lock within ${ATTACH_WAIT_SEC}s" >&2
    exit 1
  fi
  trap '_release_dir_lock "${_lock_dir}"' EXIT

  if _stack_warm; then
    echo "STACK_ENSURE_OK: already shell_hot api=:8080 ui=:3000"
    exit 0
  fi

  _ensure_backend || exit 1
  _start_frontend_supervisor || exit 1

  if ! _wait_stack_health "${ENSURE_FRONTEND_WAIT_SEC}"; then
    echo "STACK_FAIL: stack not HTTP healthy after ensure" >&2
    exit 1
  fi

  if _warmup_frontend_compile; then
    echo "STACK_ENSURE_OK: api=:8080 ui=:3000 shell_hot=yes"
    exit 0
  fi
  echo "STACK_FAIL: stack not shell_hot after ensure" >&2
  exit 1
}

cmd_reset() {
  if [[ -f "${FRONTEND_PID}" ]]; then
    local fe_pid
    fe_pid="$(cat "${FRONTEND_PID}")"
    kill "${fe_pid}" 2>/dev/null || true
    rm -f "${FRONTEND_PID}"
  fi
  rm -f "${FRONTEND_LOCK}"
  _frontend_clear_warmth
  _clear_stack_epoch

  local port="${PORT:-8080}"
  if [[ -f "${SERVER_DIR}/.myrm-dev-backend.pid" ]]; then
    local dev_pid
    dev_pid="$(cat "${SERVER_DIR}/.myrm-dev-backend.pid")"
    if kill -0 "${dev_pid}" 2>/dev/null; then
      curl -sf -X POST "http://127.0.0.1:${port}/api/v1/system/shutdown" -o /dev/null 2>/dev/null || true
      local _
      for _ in $(seq 1 10); do
        kill -0 "${dev_pid}" 2>/dev/null || break
        sleep 1
      done
      kill "${dev_pid}" 2>/dev/null || true
    fi
    rm -f "${SERVER_DIR}/.myrm-dev-backend.pid"
  fi

  if _frontend_port_listening; then
    local pids
    pids="$(lsof -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ')"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill ${pids} 2>/dev/null || true
    fi
  fi

  local stale_pids
  stale_pids="$(ps aux | grep -E '[m]yrm-agent-server/run.py|[m]yrm-agent-server/.venv.*run.py' | awk '{print $2}' || true)"
  if [[ -n "${stale_pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${stale_pids} 2>/dev/null || true
    sleep 2
    stale_pids="$(ps aux | grep -E '[m]yrm-agent-server/run.py|[m]yrm-agent-server/.venv.*run.py' | awk '{print $2}' || true)"
    if [[ -n "${stale_pids}" ]]; then
      # shellcheck disable=SC2086
      kill -9 ${stale_pids} 2>/dev/null || true
    fi
  fi

  _clear_stack_epoch

  echo "STACK_RESET_OK"
}

cmd_status() {
  local api="down" fe="down" lock="missing" shell_hot="down" stack_epoch=""
  _api_healthy 3 && api="up"
  _frontend_healthy 5 && fe="up"
  shell_hot="$(_frontend_compile_hot_status)"
  stack_epoch="$(_read_stack_epoch 2>/dev/null || true)"
  _lock_supervisor_alive && lock="alive"
  [[ -f "${FRONTEND_LOCK}" ]] && [[ "${lock}" == "missing" ]] && lock="stale"
  echo "stack_status api=${api} frontend=${fe} shell_hot=${shell_hot} client_hot=$(_frontend_client_hot_status) stack_epoch=${stack_epoch:-none} dev_lock=${lock}"
}

acquire_api_e2e_lock() {
  if _acquire_dir_lock "${_api_lock_dir}" "${API_E2E_LOCK_WAIT_SEC}"; then
    trap '_release_dir_lock "${_api_lock_dir}"' EXIT
    return 0
  fi
  echo "MYRM_API_E2E_FAIL: could not acquire api-e2e lock within ${API_E2E_LOCK_WAIT_SEC}s" >&2
  exit 1
}

usage() {
  echo "Usage: dev-stack.sh ensure|attach|reset|status" >&2
}

main() {
  local cmd="${1:-}"
  case "${cmd}" in
    ensure) cmd_ensure ;;
    attach) cmd_attach ;;
    reset) cmd_reset ;;
    status) cmd_status ;;
    ""|-h|--help) usage; exit 1 ;;
    *)
      echo "Unknown command: ${cmd}" >&2
      usage
      exit 1
      ;;
  esac
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi
