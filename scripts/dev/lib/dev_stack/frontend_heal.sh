#!/usr/bin/env bash
# Frontend restart admission of dev-stack.sh: the frontend_lifecycle gate (deterministic vs heuristic
# reasons), orphan repair, clean-restart heal and the wave stack-write assertion.
# Sourced by dev-stack.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

# --- Restart admission (frontend_lifecycle) ---------------------------------------------
# A slow Next dev server is not a dead one. Every SIGTERM of the frontend asks the gate,
# which admits heuristic restarts only on proof of a stall (flat CPU/log of the whole
# process tree, or an unhealthy episode longer than three cold compiles) and journals the
# caller and evidence. Deterministic reasons (operator reset, pause, API-binding mismatch,
# Turbopack panic residue) carry their own proof and skip the gate.
FRONTEND_GATE_HEALTHY=10
FRONTEND_GATE_DENIED=11

_frontend_restart_reason_deterministic() {
  case "$1" in
    reset | pause | binding_mismatch | panic_residue) return 0 ;;
    *) return 1 ;;
  esac
}

_frontend_lifecycle() {
  PYTHONPATH="${SCRIPT_DIR}/lib${PYTHONPATH:+:${PYTHONPATH}}" \
    "${PREFLIGHT_PY:-python3}" -m frontend_lifecycle "$@"
}

# $1 = reason. Returns 0 allow | 10 frontend healthy (do not restart) | 11 denied.
# A gate failure denies: a stuck heal is recoverable, a wrongly killed compile is not.
_frontend_restart_admit() {
  local reason="$1" rc=0
  if _frontend_restart_reason_deterministic "${reason}"; then
    return 0
  fi
  _frontend_lifecycle admit --reason "${reason}" --port "${FRONTEND_PORT}" \
    --url "${APP_URL}/" --state-dir "${STATE_DIR}" \
    --pid-file "${FRONTEND_PID}" --log-file "${FRONTEND_LOG}" || rc=$?
  case "${rc}" in
    0 | "${FRONTEND_GATE_HEALTHY}" | "${FRONTEND_GATE_DENIED}") return "${rc}" ;;
    *)
      echo "STACK_WARN: frontend restart gate error (rc=${rc}) — refusing restart (fail closed)" >&2
      return "${FRONTEND_GATE_DENIED}"
      ;;
  esac
}

_frontend_journal_kill() {
  _frontend_lifecycle journal --reason "$1" --state-dir "${STATE_DIR}" \
    --port "${FRONTEND_PORT}" --pids "${2:-}" >/dev/null 2>&1 || true
}

# Gate + kill + orphan cleanup ahead of a relaunch. $1 = reason. Returns 0 (clear to
# launch) | 10 (frontend healthy — do not launch) | 11 (denied: still compiling or not
# proven dead) | 1 (kill refused by the wave gate).
_frontend_restart_prepare() {
  local reason="$1" rc=0
  _kill_frontend_supervisor "${reason}" || rc=$?
  if [[ "${rc}" -ne 0 ]]; then
    return "${rc}"
  fi
  _repair_orphan_frontend "${reason}" || rc=$?
  return "${rc}"
}

_repair_orphan_frontend() {
  local reason="${1:-orphan}" admit_rc=0
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
  if ! _wave_assert_stack_write_allowed; then
    echo "STACK_FAIL: orphan frontend cleanup denied while wave pins stack" >&2
    return 1
  fi
  _frontend_restart_admit "${reason}" || admit_rc=$?
  if [[ "${admit_rc}" -ne 0 ]]; then
    return "${admit_rc}"
  fi
  echo "STACK_WARN: orphan :${FRONTEND_PORT} listener without dev-server.lock — clearing" >&2
  local owned_pids
  owned_pids="$(_owned_frontend_listener_pids)"
  if [[ -n "${owned_pids}" ]]; then
    _frontend_journal_kill "${reason}" "${owned_pids}"
    # shellcheck disable=SC2086
    kill ${owned_pids} 2>/dev/null || true
    sleep 1
  fi
  rm -f "${FRONTEND_PID}" "${FRONTEND_LOCK}"
}

_frontend_heal_stack_write_allowed() {
  [[ "${MYRM_CHROME_E2E_FRONTEND_HEAL:-}" == "1" ]] || [[ "${MYRM_E2E_ATTACH_FRONTEND_HEAL:-}" == "1" ]]
}

# One restart path for every "the UI answers but the client is not usable" case.
# $1 = restart reason (frontend_lifecycle.policy.Reason), $2 = label for the success marker.
# Returns 0 when the frontend is (re)started or already healthy enough to continue.
_frontend_clean_restart_heal() {
  local reason="$1"
  local label="$2"
  local gate_rc=0
  _frontend_heal_stack_write_allowed || return 1
  _frontend_restart_prepare "${reason}" || gate_rc=$?
  case "${gate_rc}" in
    0)
      _frontend_clear_warmth || true
      if _try_frontend_start_with_clean_fallback; then
        echo "STACK_FRONTEND_ONLY_ENSURE_OK: ui=:${FRONTEND_PORT} ${label}=clean_retry"
        return 0
      fi
      return 1
      ;;
    "${FRONTEND_GATE_HEALTHY}")
      # A missing hydration record is the normal state after any restart and the attach
      # flow's own CDP warmup writes it; killing a serving frontend would only cost every
      # peer a cold compile (the restart clears the record again).
      echo "STACK_FRONTEND_ONLY_ENSURE_OK: ui=:${FRONTEND_PORT} ${label}=pending"
      return 0
      ;;
  esac
  return 1
}

_wave_assert_stack_write_allowed() {
  if [[ "${MYRM_WAVE_GATE_BYPASS:-}" == "1" ]]; then
    return 0
  fi
  if _frontend_heal_stack_write_allowed; then
    return 0
  fi
  local wave_sh="${SCRIPT_DIR}/wave.sh"
  if [[ ! -f "${wave_sh}" ]]; then
    return 0
  fi
  bash "${wave_sh}" check-stack-write
}
