#!/usr/bin/env bash
# Shared dev stack health: UI and API reachability, the recovery gate before ready, the private-backend
# attach path and the stack epoch file.
# Sourced by chrome-e2e-preflight.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

_wait_shared_ui_reachable() {
  local shared_ui="$1"
  local wait_sec="${MYRM_CHROME_E2E_SHARED_UI_WAIT_SEC:-180}"
  local poll_sec="${MYRM_CHROME_E2E_SHARED_UI_POLL_SEC:-2}"
  [[ "${wait_sec}" =~ ^[0-9]+$ ]] || wait_sec=180
  [[ "${poll_sec}" =~ ^[0-9]+$ && "${poll_sec}" -gt 0 ]] || poll_sec=2
  local waited=0
  while true; do
    if curl -sf --max-time 10 "${shared_ui}/" >/dev/null; then
      ok "shared UI ${shared_ui}"
      return 0
    fi
    if [[ "${waited}" -ge 30 && $((waited % 30)) -eq 0 ]]; then
      _heal_dead_shared_ui_port
    fi
    if [[ "${waited}" -ge "${wait_sec}" ]]; then
      fail "shared UI not reachable at ${shared_ui} within ${wait_sec}s — run: ./myrm-dev ready --chrome"
    fi
    if [[ "${waited}" -eq 0 || $((waited % 10)) -eq 0 ]]; then
      echo "CHROME_E2E_WAIT: shared UI recovering ${waited}/${wait_sec}s (${shared_ui})" >&2
    fi
    _admit_poll_touch "CHROME_E2E_SHARED_UI_REACHABLE_WAIT"
    _admit_poll_budget_or_fail "CHROME_E2E_SHARED_UI_REACHABLE_WAIT" || return $?
    sleep "${poll_sec}"
    waited=$((waited + poll_sec))
  done
}

_heal_dead_shared_ui_port() {
  _heal_shared_ui_if_stale || true
}

_shared_stack_endpoints_ok() {
  local shared_ui="${E2E_UI_BASE:-${UI_BASE}}"
  curl -sf --max-time 10 "${shared_ui}/" >/dev/null \
    && curl -sf --max-time 10 "${SHARED_API_BASE}/api/v1/health" >/dev/null
}

_shared_stack_recovery_required() {
  local min_leases="${MYRM_E2E_SHARED_STACK_GATE_MIN_LEASES:-4}"
  local active_leases
  active_leases="$(_parallel_attach_active_leases)"
  [[ "${active_leases}" -ge "${min_leases}" ]] || return 1
  [[ "${MYRM_E2E_MODEL_SEED_FAILED:-0}" == "1" ]] && ! _shared_stack_endpoints_ok && return 0
  ! _shared_stack_endpoints_ok
}

_wait_shared_stack_healthy_before_ready() {
  _shared_stack_recovery_required || return 0
  local wait_sec poll_sec waited=0 wait_started=$SECONDS
  local active_leases ui_heal_during_wait=0 ui_heal_cap=2
  active_leases="$(_parallel_attach_active_leases)"
  wait_sec="$(_attach_parallel_wait_sec)"
  poll_sec="${MYRM_CHROME_E2E_SHARED_UI_POLL_SEC:-2}"
  [[ "${poll_sec}" =~ ^[0-9]+$ && "${poll_sec}" -gt 0 ]] || poll_sec=2
  if [[ "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]]; then
    ui_heal_cap=$((2 + active_leases / 3))
    if [[ "${ui_heal_cap}" -gt 6 ]]; then
      ui_heal_cap=6
    fi
  fi
  echo "CHROME_E2E_WAIT: shared stack recovery gate (leases=${active_leases}; seed_failed=${MYRM_E2E_MODEL_SEED_FAILED:-0})" >&2
  while true; do
    waited=$((SECONDS - wait_started))
    if _shared_stack_endpoints_ok; then
      if [[ "${MYRM_E2E_MODEL_SEED_FAILED:-0}" != "1" ]]; then
        ok "shared stack healthy before READY"
        return 0
      fi
      _maybe_seed_providers || true
      if [[ "${MYRM_E2E_MODEL_SEED_FAILED:-0}" != "1" ]]; then
        ok "shared stack healthy before READY (model seed recovered)"
        return 0
      fi
      # idempotent seed may time out under parallel load while the shared stack stays healthy.
      MYRM_E2E_MODEL_SEED_FAILED=0
      ok "shared stack healthy before READY (endpoints ok; parallel seed timeout non-fatal)"
      return 0
    fi
    if [[ "${waited}" -ge "${wait_sec}" ]]; then
      fail "shared stack not healthy within ${wait_sec}s (leases=${active_leases}; seed_failed=${MYRM_E2E_MODEL_SEED_FAILED:-0}) — do not stop other pytest; retry ADMIT or ./myrm-dev ui-heal when idle"
    fi
    if [[ "${waited}" -ge 30 && $((waited % 30)) -eq 0 ]]; then
      echo "E2E_SHARED_STACK_RECOVERY_WAIT: the shared stack or model seed not ready ${waited}/${wait_sec}s (leases=${active_leases}; do not stop other pytest)" >&2
      if [[ "${ui_heal_during_wait}" -lt "${ui_heal_cap}" ]]; then
        ui_heal_during_wait=$((ui_heal_during_wait + 1))
        _heal_shared_ui_if_stale || true
      fi
    fi
    _admit_poll_touch "E2E_SHARED_STACK_RECOVERY_WAIT"
    _admit_poll_budget_or_fail "E2E_SHARED_STACK_RECOVERY_WAIT" || return $?
    sleep "${poll_sec}"
  done
}

_private_backend_attach_path() {
  local shared_ui="${E2E_UI_BASE:-${UI_BASE}}"
  ok "private backend attach deferred (SHPOIB bootstrap will bind private pool)"
  _wait_shared_ui_reachable "${shared_ui}"
  _seed_providers_for_runtime
  _wait_shared_stack_healthy_before_ready || return $?
  myrm_chrome_e2e_cdp_healthy || fail "Myrm E2E Chrome CDP not reachable — run: ./myrm-dev ready --chrome"
  ok "Myrm E2E Chrome port=${MYRM_CHROME_E2E_PORT}"
  local mux_pid_file="${CDMCP_MUX_STATE_DIR:-$(real_user_home)/.local/state/cdmcp-mux}/daemon.pid"
  if [[ -f "${mux_pid_file}" ]]; then
    local mux_pid
    mux_pid="$(tr -d '[:space:]' < "${mux_pid_file}")"
    if [[ -n "${mux_pid}" ]] && kill -0 "${mux_pid}" 2>/dev/null; then
      ok "cdmcp-mux daemon pid=${mux_pid}"
    fi
  fi
  echo "CHROME_E2E_READY ui=${shared_ui} api=${API_BASE} port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
}

_ensure_stack_epoch_file() {
  local epoch_file backend_pid
  epoch_file="$(_stack_epoch_file)"
  if [[ -f "${epoch_file}" ]]; then
    return 0
  fi
  if ! curl -sf --max-time 5 "${API_BASE}/api/v1/health" >/dev/null 2>&1; then
    return 0
  fi
  backend_pid=""
  backend_pid="$(read_backend_dev_pid 2>/dev/null || true)"
  _bump_stack_epoch "${backend_pid}" "${SERVER_DIR}" >/dev/null || true
}
