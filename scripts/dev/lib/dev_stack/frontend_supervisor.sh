#!/usr/bin/env bash
# Frontend supervisor management of dev-stack.sh: detached spawn, kill, pause check, launch, stale
# next-dev-lock heal, clean-fallback start and the start entry.
# Sourced by dev-stack.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

_spawn_detached() {
  local log_file="$1"
  shift
  if command -v setsid >/dev/null 2>&1; then
    setsid nohup "$@" >>"${log_file}" 2>&1 &
  else
    # macOS has no setsid(1). Without a session of its own the child stays in the caller's
    # process group and is reaped with it when that group is signalled (agent shell, test
    # cleanup). Same launcher idea as the backend (lib/backend_bg.sh); exec keeps the pid.
    "${PREFLIGHT_PY:-python3}" -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' \
      nohup "$@" >>"${log_file}" 2>&1 &
    disown $! 2>/dev/null || true
  fi
}

# $1 = reason (frontend_lifecycle.policy.Reason; unknown/empty is treated as heuristic).
# Returns 0 killed | 1 wave gate refused | 10 frontend healthy | 11 restart denied.
_kill_frontend_supervisor() {
  local reason="${1:-unresponsive}" admit_rc=0
  if ! _wave_assert_stack_write_allowed; then
    echo "STACK_FAIL: frontend kill denied while wave pins stack" >&2
    return 1
  fi
  _frontend_restart_admit "${reason}" || admit_rc=$?
  if [[ "${admit_rc}" -ne 0 ]]; then
    return "${admit_rc}"
  fi
  local fe_pid=""
  if [[ -f "${FRONTEND_PID}" ]]; then
    fe_pid="$(_owned_pid_from_file "${FRONTEND_PID}")"
  fi
  _frontend_journal_kill "${reason}" "${fe_pid} $(_owned_frontend_listener_pids)"
  if [[ -n "${fe_pid}" ]]; then
    kill -TERM "${fe_pid}" 2>/dev/null || true
    sleep 1
    kill -9 "${fe_pid}" 2>/dev/null || true
  fi
  rm -f "${FRONTEND_PID}"
  if _frontend_port_listening; then
    local owned_pids
    owned_pids="$(_owned_frontend_listener_pids)"
    if [[ -n "${owned_pids}" ]]; then
      # shellcheck disable=SC2086
      kill -TERM ${owned_pids} 2>/dev/null || true
      sleep 1
      # shellcheck disable=SC2086
      kill -9 ${owned_pids} 2>/dev/null || true
    fi
  fi
  rm -f "${FRONTEND_LOCK}"
}

_frontend_dev_paused() {
  # Only clear-pause lifts the stamp — MYRM_FRONTEND_DEV_FORCE alone cannot bypass cleanup.
  "${PREFLIGHT_PY:-python3}" "${SCRIPT_DIR}/lib/e2e_core/frontend_dev_pause.py" check >/dev/null 2>&1
}

_launch_frontend_supervisor() {
  # Hard gate: every cold-start path goes through here (ensure / frontend-only / clean fallback).
  if _frontend_dev_paused; then
    echo "STACK_FRONTEND_SKIP: launch blocked — frontend dev paused; run: frontend-only clear-pause" >&2
    return 1
  fi
  local use_clean="${1:-0}"
  local dev_script="${MYRM_FRONTEND_DEV_SCRIPT:-${FRONTEND_DIR}/scripts/dev.ts}"
  local webpack_args=()
  if [[ "${MYRM_FRONTEND_DEV_WEBPACK:-0}" == "1" ]]; then
    webpack_args=(--webpack)
  fi
  cd "${FRONTEND_DIR}"
  # Frontend child must run under real user home so next cache/harness paths
  # don't leak into sandboxed ~/.cursor-3.
  export_spawn_home || return 1
  bash "${SCRIPT_DIR}/ensure-next-native-swc.sh"
  if [[ -f "${FRONTEND_LOG}" ]]; then
    local log_bytes=0
    log_bytes="$(wc -c <"${FRONTEND_LOG}" 2>/dev/null | tr -d '[:space:]')"
    if [[ "${log_bytes}" =~ ^[0-9]+$ && "${log_bytes}" -gt 52428800 ]]; then
      echo "STACK_HEAL: rotating oversized frontend.log (${log_bytes} bytes)" >&2
      mv "${FRONTEND_LOG}" "${FRONTEND_LOG}.1" 2>/dev/null || : >"${FRONTEND_LOG}"
    fi
  fi
  _frontend_clear_warmth
  if [[ "${use_clean}" == "1" ]]; then
    echo "STACK_START: frontend with --clean (.next purge)" >&2
    if ((${#webpack_args[@]} > 0)); then
      _spawn_detached "${FRONTEND_LOG}" env MYRM_FRONTEND_PORT="${FRONTEND_PORT}" API_PORT="${FRONTEND_API_PORT}" PORT="${FRONTEND_API_PORT}" MYRM_NEXT_DIST_DIR="${MYRM_NEXT_DIST_DIR:-.next-dev}" "${MYRM_BUN}" run "${dev_script}" --clean "${webpack_args[@]}"
    else
      _spawn_detached "${FRONTEND_LOG}" env MYRM_FRONTEND_PORT="${FRONTEND_PORT}" API_PORT="${FRONTEND_API_PORT}" PORT="${FRONTEND_API_PORT}" MYRM_NEXT_DIST_DIR="${MYRM_NEXT_DIST_DIR:-.next-dev}" "${MYRM_BUN}" run "${dev_script}" --clean
    fi
  else
    if ((${#webpack_args[@]} > 0)); then
      _spawn_detached "${FRONTEND_LOG}" env MYRM_FRONTEND_PORT="${FRONTEND_PORT}" API_PORT="${FRONTEND_API_PORT}" PORT="${FRONTEND_API_PORT}" MYRM_NEXT_DIST_DIR="${MYRM_NEXT_DIST_DIR:-.next-dev}" "${MYRM_BUN}" run "${dev_script}" "${webpack_args[@]}"
    else
      _spawn_detached "${FRONTEND_LOG}" env MYRM_FRONTEND_PORT="${FRONTEND_PORT}" API_PORT="${FRONTEND_API_PORT}" PORT="${FRONTEND_API_PORT}" MYRM_NEXT_DIST_DIR="${MYRM_NEXT_DIST_DIR:-.next-dev}" "${MYRM_BUN}" run "${dev_script}"
    fi
  fi
  echo $! >"${FRONTEND_PID}"
  echo "STACK_START: frontend supervisor pid $(cat "${FRONTEND_PID}") (setsid detached)"
}

_frontend_turbopack_panic_residue() {
  # Turbopack persistent-cache restore failure aborts the dev server mid-compile
  # ("panicked at turbopack" + "Aborting."). A non-clean cold start reuses the
  # corrupted .next cache and re-panics on later routes — force --clean instead.
  [[ -f "${FRONTEND_LOG}" ]] || return 1
  grep -qE "panicked at turbopack|turbo-tasks: an internal panic|Aborting\." "${FRONTEND_LOG}" 2>/dev/null
}

_heal_stale_next_dev_lock() {
  # Next.js dev-server.lock can reference a stale next-server PID on an alt port
  # (e.g. :13301) while the shared UI stays dead — kills the stale PID once per ensure.
  [[ -f "${FRONTEND_LOG}" ]] || return 1
  local tail_log=""
  tail_log="$(tail -n 120 "${FRONTEND_LOG}" 2>/dev/null || true)"
  [[ -n "${tail_log}" ]] || return 1
  grep -q "Another next dev server is already running" <<<"${tail_log}" || return 1
  local stale_pid=""
  stale_pid="$(grep -E '^- PID:' <<<"${tail_log}" | tail -1 | sed -E 's/^- PID:[[:space:]]+//')"
  [[ "${stale_pid}" =~ ^[0-9]+$ ]] || return 1
  if [[ -f "${FRONTEND_PID}" ]]; then
    local fe_pid=""
    fe_pid="$(tr -d '[:space:]' <"${FRONTEND_PID}")"
    if [[ "${stale_pid}" == "${fe_pid}" ]]; then
      return 1
    fi
  fi
  if ! kill -0 "${stale_pid}" 2>/dev/null; then
    return 1
  fi
  # The pid comes from a log line of an earlier run: it may have been recycled by any process, so
  # only one this stack started (the dev stamp, never the command line) is ever signalled.
  if [[ -z "$(dev_filter_owned_pids "${stale_pid}" 2>/dev/null)" ]]; then
    return 1
  fi
  echo "STACK_HEAL: stale Next.js dev lock PID ${stale_pid} — terminating orphan next-server" >&2
  kill -TERM "${stale_pid}" 2>/dev/null || true
  sleep 1
  kill -9 "${stale_pid}" 2>/dev/null || true
  return 0
}

# Returns 0 ready | 1 failed | 11 restart denied (server still compiling or not proven dead).
_try_frontend_start_with_clean_fallback() {
  local gate_rc=0
  if _frontend_turbopack_panic_residue; then
    echo "STACK_WARN: Turbopack panic residue — skip non-clean, force --clean cold start" >&2
    _kill_frontend_supervisor panic_residue || return 1
    _repair_orphan_frontend panic_residue || return 1
    _launch_frontend_supervisor 1
    if _wait_frontend_http_200 "${ENSURE_FRONTEND_WAIT_SEC}"; then
      _sync_frontend_pid_from_lock
      echo "STACK_OK: frontend → ${APP_URL} (after --clean; panic residue)"
      return 0
    fi
    echo "STACK_WARN: frontend still not HTTP 200 after --clean (panic residue) — check ${FRONTEND_LOG}" >&2
    return 1
  fi
  _launch_frontend_supervisor 0
  if _wait_frontend_http_200 "${ENSURE_FRONTEND_WAIT_SEC}"; then
    _sync_frontend_pid_from_lock
    echo "STACK_OK: frontend → ${APP_URL}"
    return 0
  fi
  local last_code
  last_code="$(_frontend_http_status)"
  if [[ "${last_code}" == "000" ]] && _heal_stale_next_dev_lock; then
    _frontend_restart_prepare unresponsive || gate_rc=$?
    case "${gate_rc}" in
      0) ;;
      "${FRONTEND_GATE_HEALTHY}") _sync_frontend_pid_from_lock; echo "STACK_OK: frontend → ${APP_URL} (healthy at restart gate)"; return 0 ;;
      "${FRONTEND_GATE_DENIED}") return "${FRONTEND_GATE_DENIED}" ;;
      *) return 1 ;;
    esac
    _launch_frontend_supervisor 0
    if _wait_frontend_http_200 "${ENSURE_FRONTEND_WAIT_SEC}"; then
      _sync_frontend_pid_from_lock
      echo "STACK_OK: frontend → ${APP_URL} (after stale next-server heal)"
      return 0
    fi
    last_code="$(_frontend_http_status)"
  fi
  if [[ "${last_code}" != "404" && "${last_code}" != "000" ]]; then
    echo "STACK_WARN: frontend slow to start (last HTTP ${last_code}) — check ${FRONTEND_LOG}" >&2
    return 1
  fi
  echo "STACK_WARN: frontend HTTP ${last_code} — retry with bun run dev --clean" >&2
  local clean_reason="unresponsive"
  [[ "${last_code}" == "404" ]] && clean_reason="bad_http"
  gate_rc=0
  _frontend_restart_prepare "${clean_reason}" || gate_rc=$?
  case "${gate_rc}" in
    0) ;;
    "${FRONTEND_GATE_HEALTHY}") _sync_frontend_pid_from_lock; echo "STACK_OK: frontend → ${APP_URL} (healthy at restart gate)"; return 0 ;;
    "${FRONTEND_GATE_DENIED}") return "${FRONTEND_GATE_DENIED}" ;;
    *) return 1 ;;
  esac
  _launch_frontend_supervisor 1
  if _wait_frontend_http_200 "${ENSURE_FRONTEND_WAIT_SEC}"; then
    _sync_frontend_pid_from_lock
    echo "STACK_OK: frontend → ${APP_URL} (after --clean)"
    return 0
  fi
  echo "STACK_WARN: frontend still not HTTP 200 after --clean — check ${FRONTEND_LOG}" >&2
  return 1
}

# Returns 0 ready | 1 failed | 11 restart denied (server still compiling or not proven dead).
_start_frontend_supervisor() {
  local gate_rc=0
  if _frontend_dev_paused; then
    if _frontend_healthy || _frontend_port_listening; then
      echo "STACK_FRONTEND_RECLAIM: pause active — stopping existing frontend on :${FRONTEND_PORT}" >&2
      _kill_frontend_supervisor pause || true
      _repair_orphan_frontend pause || true
    fi
    echo "STACK_FRONTEND_SKIP: frontend dev paused (bun run cleanup); run: frontend-only clear-pause" >&2
    return 0
  fi
  if _frontend_healthy && _frontend_binding_matches; then
    _sync_frontend_pid_from_lock
    echo "STACK_OK: frontend already healthy → ${APP_URL}"
    return 0
  fi

  if _frontend_port_listening && ! _frontend_binding_matches; then
    # Reusing this frontend would keep serving /api/v1 from the wrong backend, and the
    # compile wait below would be satisfied by the same stale process. Stop it so the
    # launch path starts a fresh server with the current API_PORT.
    _kill_frontend_supervisor binding_mismatch || return 1
  fi

  if _lock_supervisor_alive; then
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
      _frontend_restart_prepare bad_http || gate_rc=$?
      case "${gate_rc}" in
        0) _try_frontend_start_with_clean_fallback || return $?; return 0 ;;
        "${FRONTEND_GATE_HEALTHY}") _sync_frontend_pid_from_lock; echo "STACK_OK: frontend ready (healthy at restart gate)"; return 0 ;;
        "${FRONTEND_GATE_DENIED}") return "${FRONTEND_GATE_DENIED}" ;;
      esac
    fi
    return 1
  fi

  _repair_orphan_frontend orphan || gate_rc=$?
  case "${gate_rc}" in
    0) ;;
    "${FRONTEND_GATE_HEALTHY}") _sync_frontend_pid_from_lock; echo "STACK_OK: frontend ready (healthy at restart gate)"; return 0 ;;
    "${FRONTEND_GATE_DENIED}") return "${FRONTEND_GATE_DENIED}" ;;
    *) return 1 ;;
  esac

  if [[ -z "${MYRM_BUN}" ]]; then
    echo "STACK_FAIL: bun not found — run: myrm setup" >&2
    return 1
  fi

  _try_frontend_start_with_clean_fallback
}
