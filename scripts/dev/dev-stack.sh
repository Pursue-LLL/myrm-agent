#!/usr/bin/env bash
# Dev stack lifecycle — ensure/attach/reset/status for local :8080/:3000.
# Mutations delegate to stack_supervisor daemon; only its direct child may enter internals.
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
# shellcheck source=lib/dev_state_paths.sh
source "${SCRIPT_DIR}/lib/dev_state_paths.sh"
resolve_agent_paths "${REPO_ROOT}"

STATE_DIR="${MYRM_DEV_STATE_DIR:-${HOME}/.local/state/myrm-dev}"
BACKEND_PORT="${MYRM_BACKEND_PORT:-${PORT:-8080}}"
FRONTEND_PORT="${MYRM_FRONTEND_PORT:-3000}"
APP_URL="${E2E_UI_BASE:-http://127.0.0.1:${FRONTEND_PORT}}"
API_BASE="${E2E_API_BASE:-http://127.0.0.1:${BACKEND_PORT}}"
API_HEALTH="${API_BASE}/api/v1/health"

BACKEND_PID="${MYRM_BACKEND_PID_FILE:-${STATE_DIR}/backend.pid}"
BACKEND_LOG="${MYRM_BACKEND_LOG_FILE:-${STATE_DIR}/backend.log}"
BACKEND_IDENTITY="${MYRM_BACKEND_IDENTITY_FILE:-${STATE_DIR}/backend-process.json}"
FRONTEND_PID="${MYRM_FRONTEND_PID_FILE:-${STATE_DIR}/frontend.pid}"
FRONTEND_LOG="${MYRM_FRONTEND_LOG_FILE:-${STATE_DIR}/frontend.log}"
export STATE_DIR PORT="${BACKEND_PORT}" MYRM_BACKEND_PORT="${BACKEND_PORT}"
export MYRM_FRONTEND_PORT="${FRONTEND_PORT}" API_PORT="${BACKEND_PORT}"
export E2E_UI_BASE="${APP_URL}" E2E_API_BASE="${API_BASE}"
export MYRM_BACKEND_PID_FILE="${BACKEND_PID}" MYRM_BACKEND_LOG_FILE="${BACKEND_LOG}"
export MYRM_BACKEND_IDENTITY_FILE="${BACKEND_IDENTITY}"

ENSURE_FRONTEND_WAIT_SEC="${MYRM_STACK_FRONTEND_WAIT_SEC:-180}"
# Wait budget must cover a full ensure (frontend cold compile) plus lock handoff.
ATTACH_WAIT_SEC="${MYRM_STACK_ATTACH_WAIT_SEC:-$((ENSURE_FRONTEND_WAIT_SEC + 60))}"

mkdir -p "${STATE_DIR}"
export_myrm_next_dist_dir
if [[ "${STATE_DIR}" != "${HOME}/.local/state/myrm-dev" ]]; then
  export MYRM_FRONTEND_DEV_WEBPACK=1
fi
mkdir -p "${FRONTEND_DIR}/${MYRM_NEXT_DIST_DIR}"
FRONTEND_LOCK="$(resolve_frontend_lock_path "${FRONTEND_DIR}")"

_lock_dir="${STATE_DIR}/ensure.lock.d"

_acquire_dir_lock() {
  local lockdir="$1"
  local wait_sec="$2"
  local i

  if [[ -d "${lockdir}" ]]; then
    local owner=""
    if [[ -f "${lockdir}/pid" ]]; then
      owner="$(tr -d '[:space:]' <"${lockdir}/pid")"
    fi
    if [[ -n "${owner}" ]] && kill -0 "${owner}" 2>/dev/null; then
      local lock_mtime now age
      lock_mtime="$(stat -f %m "${lockdir}/pid" 2>/dev/null || stat -c %Y "${lockdir}/pid" 2>/dev/null || echo 0)"
      now="$(date +%s)"
      age=$((now - lock_mtime))
      if [[ "${age}" -gt "${wait_sec}" ]]; then
        echo "STACK_WARN: reclaiming hung lock ${lockdir} owner=${owner} age=${age}s" >&2
        kill -TERM "${owner}" 2>/dev/null || true
        sleep 1
        _release_dir_lock "${lockdir}"
      fi
    elif [[ -z "${owner}" ]] || ! kill -0 "${owner}" 2>/dev/null; then
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

_ensure_lock_owner_alive() {
  local lockdir="$1"
  local owner=""

  [[ -d "${lockdir}" ]] || return 1
  if [[ -f "${lockdir}/pid" ]]; then
    owner="$(tr -d '[:space:]' <"${lockdir}/pid")"
  fi
  [[ -n "${owner}" ]] && kill -0 "${owner}" 2>/dev/null
}

_join_ensure_in_progress() {
  local lockdir="$1"
  local wait_sec="$2"
  local owner=""

  if ! _ensure_lock_owner_alive "${lockdir}"; then
    return 1
  fi
  owner="$(tr -d '[:space:]' <"${lockdir}/pid")"
  echo "STACK_JOIN: ensure in progress (pid=${owner}) — waiting for shell_hot" >&2
  if _wait_stack_warm "${wait_sec}"; then
    _try_optional_client_hot
    echo "STACK_ENSURE_OK: joined in-progress ensure api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=yes"
    return 0
  fi
  return 1
}

_http_ok() {
  local url="$1"
  local max_time="${2:-8}"
  curl -sf --max-time "${max_time}" "${url}" >/dev/null 2>&1
}

_frontend_http_status() {
  curl -s -o /dev/null -w "%{http_code}" --max-time 8 "${APP_URL}/" 2>/dev/null || echo "000"
}

_wait_frontend_http_200() {
  local max="${1:-${ENSURE_FRONTEND_WAIT_SEC}}"
  local i code port_seen=0
  for i in $(seq 1 "${max}"); do
    if _frontend_port_listening; then
      port_seen=1
    fi
    code="$(_frontend_http_status)"
    if [[ "${code}" == "200" ]]; then
      return 0
    fi
    if [[ -f "${FRONTEND_PID}" ]]; then
      local supervisor_pid
      supervisor_pid="$(tr -d '[:space:]' <"${FRONTEND_PID}")"
      if [[ -n "${supervisor_pid}" ]] && ! kill -0 "${supervisor_pid}" 2>/dev/null; then
        echo "STACK_WARN: frontend supervisor exited before HTTP readiness — check ${FRONTEND_LOG}" >&2
        return 1
      fi
    fi
    if [[ "${port_seen}" -eq 1 ]] && [[ "${i}" == "1" || $((i % 15)) -eq 0 ]]; then
      echo "STACK_WAIT: frontend GET / → HTTP ${code} (${i}/${max}s, cold compile tolerated)..." >&2
    fi
    sleep 1
  done
  if [[ "${port_seen}" -eq 1 ]]; then
    echo "STACK_WARN: :${FRONTEND_PORT} listening but GET / never returned 200 (last=${code})" >&2
  else
    echo "STACK_WARN: :${FRONTEND_PORT} never listened within ${max}s" >&2
  fi
  return 1
}

_spawn_detached() {
  local log_file="$1"
  shift
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup "$@" >>"${log_file}" 2>&1 &
  else
    nohup "$@" >>"${log_file}" 2>&1 &
  fi
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
  _backend_supervisor_alive || return 1
  _lock_supervisor_alive || return 1
  _api_healthy 5 || return 1
  _frontend_healthy 8 || return 1
  [[ "$(_frontend_compile_hot_status)" == "yes" ]]
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

_backend_supervisor_alive() {
  [[ -f "${BACKEND_PID}" ]] || return 1
  local pid
  pid="$(tr -d '[:space:]' <"${BACKEND_PID}")"
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
  if ! _wave_assert_stack_write_allowed; then
    echo "STACK_FAIL: orphan frontend cleanup denied while wave pins stack" >&2
    return 1
  fi
  local pids
  pids="$(lsof -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ')"
  if [[ -n "${pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${pids} 2>/dev/null || true
    sleep 1
  fi
  rm -f "${FRONTEND_PID}" "${FRONTEND_LOCK}"
}

_wave_assert_stack_write_allowed() {
  if [[ "${MYRM_WAVE_GATE_BYPASS:-}" == "1" ]]; then
    return 0
  fi
  local wave_sh="${SCRIPT_DIR}/wave.sh"
  if [[ ! -f "${wave_sh}" ]]; then
    return 0
  fi
  bash "${wave_sh}" check-stack-write
}

_kill_frontend_supervisor() {
  if ! _wave_assert_stack_write_allowed; then
    echo "STACK_FAIL: frontend kill denied while wave pins stack" >&2
    return 1
  fi
  if [[ -f "${FRONTEND_PID}" ]]; then
    local fe_pid
    fe_pid="$(tr -d '[:space:]' <"${FRONTEND_PID}")"
    if [[ -n "${fe_pid}" ]]; then
      kill -TERM "${fe_pid}" 2>/dev/null || true
      sleep 1
      kill -9 "${fe_pid}" 2>/dev/null || true
    fi
    rm -f "${FRONTEND_PID}"
  fi
  if _frontend_port_listening; then
    local pids
    pids="$(lsof -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ')"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill -TERM ${pids} 2>/dev/null || true
      sleep 1
      # shellcheck disable=SC2086
      kill -9 ${pids} 2>/dev/null || true
    fi
  fi
  rm -f "${FRONTEND_LOCK}"
}

_launch_frontend_supervisor() {
  local use_clean="${1:-0}"
  local dev_script="${MYRM_FRONTEND_DEV_SCRIPT:-${FRONTEND_DIR}/scripts/dev.ts}"
  local webpack_args=()
  if [[ "${MYRM_FRONTEND_DEV_WEBPACK:-0}" == "1" ]]; then
    webpack_args=(--webpack)
  fi
  cd "${FRONTEND_DIR}"
  bash "${SCRIPT_DIR}/ensure-next-native-swc.sh"
  _frontend_clear_warmth
  if [[ "${use_clean}" == "1" ]]; then
    echo "STACK_START: frontend with --clean (.next purge)" >&2
    _spawn_detached "${FRONTEND_LOG}" env MYRM_FRONTEND_PORT="${FRONTEND_PORT}" API_PORT="${BACKEND_PORT}" MYRM_NEXT_DIST_DIR="${MYRM_NEXT_DIST_DIR:-.next}" bun run "${dev_script}" --clean "${webpack_args[@]}"
  else
    _spawn_detached "${FRONTEND_LOG}" env MYRM_FRONTEND_PORT="${FRONTEND_PORT}" API_PORT="${BACKEND_PORT}" MYRM_NEXT_DIST_DIR="${MYRM_NEXT_DIST_DIR:-.next}" bun run "${dev_script}" "${webpack_args[@]}"
  fi
  echo $! >"${FRONTEND_PID}"
  echo "STACK_START: frontend supervisor pid $(cat "${FRONTEND_PID}") (setsid detached)"
}

_try_frontend_start_with_clean_fallback() {
  _launch_frontend_supervisor 0
  if _wait_frontend_http_200 "${ENSURE_FRONTEND_WAIT_SEC}"; then
    _sync_frontend_pid_from_lock
    echo "STACK_OK: frontend → ${APP_URL}"
    return 0
  fi
  local last_code
  last_code="$(_frontend_http_status)"
  if [[ "${last_code}" != "404" && "${last_code}" != "000" ]]; then
    echo "STACK_WARN: frontend slow to start (last HTTP ${last_code}) — check ${FRONTEND_LOG}" >&2
    return 1
  fi
  echo "STACK_WARN: frontend HTTP ${last_code} — retry with bun run dev --clean" >&2
  _kill_frontend_supervisor
  _repair_orphan_frontend
  _launch_frontend_supervisor 1
  if _wait_frontend_http_200 "${ENSURE_FRONTEND_WAIT_SEC}"; then
    _sync_frontend_pid_from_lock
    echo "STACK_OK: frontend → ${APP_URL} (after --clean)"
    return 0
  fi
  echo "STACK_WARN: frontend still not HTTP 200 after --clean — check ${FRONTEND_LOG}" >&2
  return 1
}

_start_frontend_supervisor() {
  if _frontend_healthy; then
    _sync_frontend_pid_from_lock
    echo "STACK_OK: frontend already healthy → ${APP_URL}"
    return 0
  fi

  if _frontend_port_listening && _lock_supervisor_alive; then
    echo "STACK_WAIT: frontend compiling — up to ${ENSURE_FRONTEND_WAIT_SEC}s..."
    if _wait_frontend_http_200 "${ENSURE_FRONTEND_WAIT_SEC}"; then
      _sync_frontend_pid_from_lock
      echo "STACK_OK: frontend ready after compile wait"
      return 0
    fi
    echo "STACK_WARN: frontend still not HTTP-ready after compile wait — check ${FRONTEND_LOG}" >&2
    local last_code
    last_code="$(_frontend_http_status)"
    if [[ "${last_code}" == "404" ]]; then
      echo "STACK_WARN: compile wait got HTTP 404 — retry with --clean" >&2
      _kill_frontend_supervisor
      _repair_orphan_frontend
      _try_frontend_start_with_clean_fallback && return 0
    fi
    return 1
  fi

  _repair_orphan_frontend

  if ! command -v bun >/dev/null 2>&1; then
    echo "STACK_FAIL: bun not found — run: myrm setup" >&2
    return 1
  fi

  _try_frontend_start_with_clean_fallback
}

_ensure_backend() {
  if ! _start_backend_bg "${SERVER_DIR}"; then
    echo "STACK_FAIL: backend start failed" >&2
    return 1
  fi
  if _api_healthy 10; then
    echo "STACK_OK: backend → ${API_BASE}"
    return 0
  fi
  echo "STACK_FAIL: backend not healthy after start" >&2
  return 1
}

cmd_attach() {
  local attach_start="${SECONDS}"
  local elapsed remaining
  if _stack_healthy; then
    echo "STACK_ATTACH_OK api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=http"
    exit 0
  fi
  if _wait_stack_warm "${ATTACH_WAIT_SEC}"; then
    echo "STACK_ATTACH_OK api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=yes"
    exit 0
  fi
  elapsed=$((SECONDS - attach_start))
  remaining=$((ATTACH_WAIT_SEC - elapsed))
  if (( remaining > 0 )) && _wait_stack_health "${remaining}"; then
    echo "STACK_ATTACH_OK api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=http"
    exit 0
  fi
  echo "STACK_ATTACH_TIMEOUT: stack not healthy within ${ATTACH_WAIT_SEC}s — run: ./myrm ready" >&2
  exit 1
}

_try_optional_client_hot() {
  local cdp_port="${MYRM_CHROME_E2E_PORT:-9333}"
  local py="${SERVER_DIR}/.venv/bin/python"
  if ! curl -sf --max-time 2 "http://127.0.0.1:${cdp_port}/json/version" >/dev/null 2>&1; then
    return 0
  fi
  if [[ ! -x "${py}" ]]; then
    py="python3"
  fi
  export MYRM_CHROME_E2E_PORT="${cdp_port}"
  export PREFLIGHT_PY="${py}"
  unset MYRM_CHROME_E2E_ATTACH
  if _warmup_frontend_client; then
    echo "STACK_OK: client_hot during ensure"
    return 0
  fi
  echo "STACK_WARN: client_hot failed during ensure — run: ./myrm ready --chrome" >&2
  return 0
}

cmd_ensure() {
  if _stack_warm; then
    _try_optional_client_hot
    echo "STACK_ENSURE_OK: already shell_hot api=:${BACKEND_PORT} ui=:${FRONTEND_PORT}"
    exit 0
  fi

  if ! _wave_assert_stack_write_allowed; then
    if _frontend_port_listening || _api_healthy 5; then
      echo "STACK_JOIN: ensure deferred — wave/lease active; attach-wait for shell_hot" >&2
      if _wait_stack_warm "${ATTACH_WAIT_SEC}"; then
        _try_optional_client_hot
        echo "STACK_ENSURE_OK: attach-wait during wave pin api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=yes"
        exit 0
      fi
      echo "STACK_ATTACH_TIMEOUT: stack not shell_hot within ${ATTACH_WAIT_SEC}s during wave pin" >&2
      exit 1
    fi
    echo "STACK_FAIL: ensure denied while wave pins stack — use: ./myrm ready --attach --chrome" >&2
    exit 1
  fi

  if _join_ensure_in_progress "${_lock_dir}" "${ATTACH_WAIT_SEC}"; then
    exit 0
  fi

  if ! _acquire_dir_lock "${_lock_dir}" "${ATTACH_WAIT_SEC}"; then
    if _wait_stack_warm "${ATTACH_WAIT_SEC}"; then
      _try_optional_client_hot
      echo "STACK_ENSURE_OK: joined late ensure api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=yes"
      exit 0
    fi
    echo "STACK_FAIL: could not acquire stack ensure lock within ${ATTACH_WAIT_SEC}s" >&2
    exit 1
  fi
  trap '_release_dir_lock "${_lock_dir}"' EXIT

  if _stack_warm; then
    _try_optional_client_hot
    echo "STACK_ENSURE_OK: already shell_hot api=:${BACKEND_PORT} ui=:${FRONTEND_PORT}"
    exit 0
  fi

  _ensure_backend || exit 1
  _start_frontend_supervisor || exit 1

  if ! _wait_stack_health "${ENSURE_FRONTEND_WAIT_SEC}"; then
    if ! _api_healthy 5 || ! _wait_frontend_http_200 30; then
      echo "STACK_FAIL: stack not HTTP healthy after ensure" >&2
      exit 1
    fi
  fi

  if _warmup_frontend_compile; then
    _try_optional_client_hot
    echo "STACK_ENSURE_OK: api=:${BACKEND_PORT} ui=:${FRONTEND_PORT} shell_hot=yes"
    exit 0
  fi
  echo "STACK_FAIL: stack not shell_hot after ensure" >&2
  exit 1
}

cmd_reset() {
  _wave_assert_stack_write_allowed || exit 3

  if [[ -f "${FRONTEND_PID}" ]]; then
    local fe_pid
    fe_pid="$(cat "${FRONTEND_PID}")"
    kill "${fe_pid}" 2>/dev/null || true
    rm -f "${FRONTEND_PID}"
  fi
  rm -f "${FRONTEND_LOCK}"
  _frontend_clear_warmth
  _clear_stack_epoch

  if [[ -f "${BACKEND_PID}" ]]; then
    local dev_pid
    dev_pid="$(cat "${BACKEND_PID}")"
    if kill -0 "${dev_pid}" 2>/dev/null; then
      kill -TERM "${dev_pid}" 2>/dev/null || true
      local _
      for _ in $(seq 1 15); do
        kill -0 "${dev_pid}" 2>/dev/null || break
        sleep 1
      done
      if kill -0 "${dev_pid}" 2>/dev/null; then
        kill -9 "${dev_pid}" 2>/dev/null || true
      fi
    fi
    rm -f "${BACKEND_PID}"
  fi

  if _frontend_port_listening; then
    local pids
    pids="$(lsof -iTCP:"${FRONTEND_PORT}" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ')"
    if [[ -n "${pids}" ]]; then
      # shellcheck disable=SC2086
      kill ${pids} 2>/dev/null || true
    fi
  fi

  local backend_listener_pids
  backend_listener_pids="$(lsof -iTCP:"${BACKEND_PORT}" -sTCP:LISTEN -t 2>/dev/null | tr '\n' ' ' || true)"
  if [[ -n "${backend_listener_pids}" ]]; then
    # shellcheck disable=SC2086
    kill ${backend_listener_pids} 2>/dev/null || true
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

_stop_private_backend() {
  local py="${SERVER_DIR}/.venv/bin/python"
  local identity_helper="${SCRIPT_DIR}/lib/process_identity.py"
  local runtime_id="${MYRM_RUNTIME_NAMESPACE:-shared}"
  if [[ ! -x "${py}" ]]; then
    py="python3"
  fi
  if [[ -f "${BACKEND_IDENTITY}" ]]; then
    if ! "${py}" "${identity_helper}" terminate \
      --identity-file "${BACKEND_IDENTITY}" \
      --pid-file "${BACKEND_PID}" \
      --expected-runtime-id "${runtime_id}"; then
      echo "STACK_FAIL: private backend process ownership mismatch" >&2
      return 1
    fi
  elif [[ -f "${BACKEND_PID}" ]] || dev_port_in_use "${BACKEND_PORT}"; then
    echo "STACK_FAIL: private backend ownership identity missing; refusing to kill pid/port" >&2
    return 1
  fi
  if ! dev_wait_ports_released 45 "${BACKEND_PORT}"; then
    echo "STACK_FAIL: private backend port :${BACKEND_PORT} still owned by an unknown listener" >&2
    return 1
  fi
  _clear_stack_epoch
}

_private_backend_identity_valid() {
  [[ -f "${BACKEND_PID}" && -f "${BACKEND_IDENTITY}" ]] || return 1
  local dev_pid py="${SERVER_DIR}/.venv/bin/python"
  dev_pid="$(tr -d '[:space:]' <"${BACKEND_PID}")"
  [[ "${dev_pid}" =~ ^[0-9]+$ ]] || return 1
  if [[ ! -x "${py}" ]]; then
    py="python3"
  fi
  "${py}" "${SCRIPT_DIR}/lib/process_identity.py" verify \
    --identity-file "${BACKEND_IDENTITY}" \
    --expected-pid "${dev_pid}" \
    --expected-runtime-id "${MYRM_RUNTIME_NAMESPACE:-shared}" >/dev/null
}

cmd_backend_only_ensure() {
  if _api_healthy 5; then
    if ! _private_backend_identity_valid; then
      echo "STACK_FAIL: healthy private port lacks matching process ownership" >&2
      exit 1
    fi
    echo "STACK_OK: private backend already healthy → ${API_BASE}"
    echo "STACK_BACKEND_ONLY_ENSURE_OK: api=:${BACKEND_PORT} ui=shared:${FRONTEND_PORT}"
    exit 0
  fi

  if ! _ensure_backend; then
    echo "STACK_FAIL: private backend start failed" >&2
    exit 1
  fi

  if _api_healthy 30; then
    echo "STACK_BACKEND_ONLY_ENSURE_OK: api=:${BACKEND_PORT} ui=shared:${FRONTEND_PORT}"
    exit 0
  fi
  echo "STACK_FAIL: private backend not healthy after ensure" >&2
  exit 1
}

cmd_backend_only_stop() {
  if ! _stop_private_backend; then
    exit 1
  fi
  echo "STACK_BACKEND_ONLY_STOP_OK"
}

usage() {
  echo "Usage: dev-stack.sh ensure|attach|reset|status|backend-only ensure|backend-only stop" >&2
}

_supervisor_delegate_or_fail() {
  local cmd="$1"
  if bash "${SCRIPT_DIR}/stack-supervisor.sh" rpc "${cmd}"; then
    return 0
  fi
  echo "STACK_FAIL: supervisor rpc ${cmd} failed — run: bash ${SCRIPT_DIR}/stack-supervisor.sh start && cd open-perplexity && ./myrm ready" >&2
  exit 1
}

_supervisor_internal_call() {
  local supervisor_pid_file="${STATE_DIR}/supervisor.pid" supervisor_pid=""
  [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" ]] || return 1
  [[ -f "${supervisor_pid_file}" ]] || return 1
  supervisor_pid="$(tr -d '[:space:]' <"${supervisor_pid_file}")"
  [[ "${supervisor_pid}" =~ ^[0-9]+$ ]] || return 1
  [[ "${supervisor_pid}" == "${PPID}" ]] || return 1
  kill -0 "${supervisor_pid}" 2>/dev/null
}

main() {
  local cmd="${1:-}"
  case "${cmd}" in
    ensure)
      if _supervisor_internal_call; then cmd_ensure; exit $?; fi
      if [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" ]]; then cmd_ensure; exit $?; fi
      _supervisor_delegate_or_fail ensure
      ;;
    attach)
      if _supervisor_internal_call; then cmd_attach; exit $?; fi
      if [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" ]]; then cmd_attach; exit $?; fi
      _supervisor_delegate_or_fail attach
      ;;
    reset)
      if _supervisor_internal_call; then cmd_reset; exit $?; fi
      if [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" ]]; then cmd_reset; exit $?; fi
      _supervisor_delegate_or_fail reset
      ;;
    status)
      if _supervisor_internal_call; then cmd_status; exit $?; fi
      if [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" ]]; then cmd_status; exit $?; fi
      _supervisor_delegate_or_fail status
      ;;
    backend-only)
      local subcmd="${2:-}"
      case "${subcmd}" in
        ensure)
          if _supervisor_internal_call; then cmd_backend_only_ensure; exit $?; fi
          if [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" || "${MYRM_WAVE_GATE_BYPASS:-}" == "1" ]]; then
            cmd_backend_only_ensure
            exit $?
          fi
          echo "STACK_FAIL: backend-only ensure requires MYRM_SUPERVISOR_BYPASS=1 or MYRM_WAVE_GATE_BYPASS=1" >&2
          exit 1
          ;;
        stop)
          if _supervisor_internal_call; then cmd_backend_only_stop; exit $?; fi
          if [[ "${MYRM_SUPERVISOR_BYPASS:-}" == "1" || "${MYRM_WAVE_GATE_BYPASS:-}" == "1" ]]; then
            cmd_backend_only_stop
            exit $?
          fi
          echo "STACK_FAIL: backend-only stop requires MYRM_SUPERVISOR_BYPASS=1 or MYRM_WAVE_GATE_BYPASS=1" >&2
          exit 1
          ;;
        *)
          echo "Unknown backend-only command: ${subcmd}" >&2
          usage
          exit 1
          ;;
      esac
      ;;
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
