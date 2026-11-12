#!/usr/bin/env bash
# Attach waits: the wave-lease count, the bootstrap clock, the bounded wait for the shared UI and API
# under parallel load and the epoch-pin shortcuts that spare an isolated attach that wait.
# Sourced by chrome-e2e-preflight.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash
# shellcheck disable=SC2153  # UI_BASE is assigned by the entry

_parallel_attach_active_leases() {
  local active_leases
  active_leases="$(_wave_active_lease_count "${MONOREPO_ROOT}")"
  [[ "${active_leases}" =~ ^[0-9]+$ ]] || active_leases=0
  if [[ "${active_leases}" -le 0 ]]; then
    active_leases="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_session_runtime.registry import list_live_e2e_sessions
print(len(list_live_e2e_sessions()))
" 2>/dev/null || echo 0)"
    [[ "${active_leases}" =~ ^[0-9]+$ ]] || active_leases=0
  fi
  echo "${active_leases}"
}

_bootstrap_attach_begin() {
  local active_leases="${1:-0}"
  [[ "${active_leases}" =~ ^[0-9]+$ ]] || active_leases=0
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -m e2e_core.bootstrap_deadline begin --active-leases "${active_leases}" >/dev/null
}

_bootstrap_attach_remaining_sec() {
  local remaining
  remaining="$(
    PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
      "${PREFLIGHT_PY}" -m e2e_core.bootstrap_deadline remaining 2>/dev/null || echo 0
  )"
  [[ "${remaining}" =~ ^[0-9]+$ ]] || remaining=0
  echo "${remaining}"
}

_wait_attach_endpoints_under_parallel_load() {
  local initial_errors="$1"
  [[ -n "${initial_errors}" ]] || return 0
  local active_leases wait_sec poll_sec waited errors heal_during_wait=0 ui_heal_during_wait=0
  active_leases="$(_parallel_attach_active_leases)"
  # UBDP-5: wave idle — no synthetic lease (retired); cap endpoint wait separately.
  _bootstrap_attach_begin "${active_leases}"
  bootstrap_budget="$(_bootstrap_attach_remaining_sec)"
  wait_sec="${bootstrap_budget}"
  if [[ "${active_leases}" -le 0 && "${E2E_SIGNOFF:-}" != "1" ]]; then
    local idle_cap="${MYRM_CHROME_E2E_IDLE_ATTACH_WAIT_SEC:-10}"
    [[ "${idle_cap}" =~ ^[0-9]+$ && "${idle_cap}" -gt 0 ]] || idle_cap=10
    if [[ "${wait_sec}" -gt "${idle_cap}" ]]; then
      wait_sec="${idle_cap}"
    fi
    echo "CHROME_E2E_ATTACH: wave idle endpoint wait cap=${wait_sec}s (UBDP-5)" >&2
  fi
  poll_sec="${MYRM_CHROME_E2E_ATTACH_POLL_SEC:-2}"
  [[ "${poll_sec}" =~ ^[0-9]+$ && "${poll_sec}" -gt 0 ]] || poll_sec=2
  local wait_started=$SECONDS
  waited=0
  local ui_heal_cap=2 ui_heal_timeout_sec=60 ui_heal_post_ensure_max_sec=120 ui_heal_next_at=30 api_heal_next_at=30
  if [[ "${active_leases}" =~ ^[0-9]+$ && "${active_leases}" -gt 0 ]]; then
    ui_heal_cap=$((2 + active_leases / 3))
    if [[ "${ui_heal_cap}" -gt 6 ]]; then
      ui_heal_cap=6
    fi
    ui_heal_timeout_sec="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from dev_gate.contract import attach_ui_heal_timeout_sec
print(attach_ui_heal_timeout_sec(${active_leases}))
")"
    ui_heal_post_ensure_max_sec="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from dev_gate.contract import attach_ui_heal_post_ensure_max_sec
print(attach_ui_heal_post_ensure_max_sec(${active_leases}))
")"
    [[ "${ui_heal_timeout_sec}" =~ ^[0-9]+$ ]] || ui_heal_timeout_sec=300
    [[ "${ui_heal_post_ensure_max_sec}" =~ ^[0-9]+$ ]] || ui_heal_post_ensure_max_sec=120
  fi
  local attach_api
  attach_api="$(_attach_api_base)"
  local epoch_pin_reseed=0 epoch_pin_reseed_max=3
  while true; do
    waited=$((SECONDS - wait_started))
    errors="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_core.endpoint_health import attach_wait_errors
print(', '.join(attach_wait_errors('${UI_BASE}', '${attach_api}')))
")"
    [[ -z "${errors}" ]] && return 0
    # A listener this stack did not start never becomes the dev backend, so waiting cannot help.
    [[ "${errors}" == *"api=foreign_listener"* ]] && return 1
    wait_sec="$(_bootstrap_attach_remaining_sec)"
    if [[ "${wait_sec}" -le 0 ]]; then
      printf '%s\n' "${errors}" >&2
      if [[ "${errors}" == *"ui=half_dead"* ]]; then
        echo "E2E_ATTACH_UI_HALF_DEAD_QUEUE: attach ADMIT waited ${wait_sec}s — shared UI still half_dead; leases=${active_leases} (do not stop other pytest; pending heal when idle)" >&2
      fi
      return 1
    fi
    if [[ "${MYRM_E2E_EPOCH_PIN:-0}" == "1" ]] \
      && [[ "${errors}" == *"api=unreachable"* ]] \
      && [[ "${epoch_pin_reseed}" -lt "${epoch_pin_reseed_max}" ]]; then
      epoch_pin_reseed=$((epoch_pin_reseed + 1))
      if _epoch_pin_reseed_verify_api; then
        attach_api="$(_attach_api_base)"
        continue
      fi
    fi
    if [[ "${MYRM_E2E_EPOCH_PIN:-0}" == "1" ]] \
      && [[ "${attach_api}" != "${SHARED_API_BASE}" ]] \
      && [[ "${errors}" == *"api=unreachable"* ]] \
      && curl -sf --max-time 5 "${SHARED_API_BASE%/}/api/v1/health" >/dev/null 2>&1; then
      echo "CHROME_E2E_ATTACH: epoch pin shared fallback during ADMIT wait api=${SHARED_API_BASE} (isolated ${attach_api} unreachable)" >&2
      unset MYRM_E2E_EPOCH_PIN
      export E2E_API_BASE="${SHARED_API_BASE}"
      attach_api="${SHARED_API_BASE}"
      API_BASE="${SHARED_API_BASE}"
      continue
    fi
    if [[ "${MYRM_PRIVATE_BACKEND:-}" != "1" ]] \
      && [[ "${MYRM_E2E_EPOCH_PIN:-0}" != "1" ]] \
      && [[ "${errors}" == *"api=unreachable"* ]] \
      && [[ "${waited}" -ge "${api_heal_next_at}" ]] \
      && [[ "${heal_during_wait}" -lt 2 ]] \
      && [[ -f "${SCRIPT_DIR}/dev-stack.sh" ]]; then
      heal_during_wait=$((heal_during_wait + 1))
      api_heal_next_at=$((api_heal_next_at + 30))
      echo "CHROME_E2E_ATTACH_HEAL: api unreachable during attach wait — retry crash heal ${heal_during_wait}/2" >&2
      if _smp_attach_backend_crash_heal "${MONOREPO_ROOT}" "${SCRIPT_DIR}/dev-stack.sh"; then
        continue
      fi
    fi
    if [[ "${errors}" == *"ui=half_dead"* || "${errors}" == *"ui=unreachable"* ]] \
      && "${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_core.warm_shell_registry import platform_shell_fresh
raise SystemExit(0 if platform_shell_fresh(route_path='/') else 1)
" 2>/dev/null; then
      echo "CHROME_E2E_ATTACH: epoch warm shell fresh — skip per-lane ui heal (§19.11 TAB-6b)" >&2
      _admit_poll_touch "CHROME_E2E_ATTACH_WARM_SHELL_FRESH"
      _admit_poll_budget_or_fail "CHROME_E2E_ATTACH_WARM_SHELL_FRESH" || return $?
      sleep "${poll_sec}"
      continue
    fi
    if [[ "${errors}" == *"ui=half_dead"* || "${errors}" == *"ui=unreachable"* ]] \
      && [[ "${waited}" -ge "${ui_heal_next_at}" ]] \
      && [[ "${ui_heal_during_wait:-0}" -lt "${ui_heal_cap}" ]]; then
      ui_heal_during_wait=$((ui_heal_during_wait + 1))
      ui_heal_next_at=$((ui_heal_next_at + 30))
      echo "CHROME_E2E_ATTACH_HEAL: ui half_dead during attach queue — bounded frontend heal ${ui_heal_during_wait}/${ui_heal_cap} (do not stop other pytest)" >&2
      if command -v timeout >/dev/null 2>&1; then
        timeout "${ui_heal_timeout_sec}" env \
          SCRIPT_DIR="${SCRIPT_DIR}" UI_BASE="${UI_BASE}" FRONTEND_PORT="${FRONTEND_PORT}" \
          MYRM_DEV_STACK="${MYRM_DEV_STACK}" MYRM_DEV_STATE_DIR="${STATE_DIR}" \
          MYRM_FRONTEND_DIR="${FRONTEND_DIR}" \
          MYRM_UI_HEAL_POST_ENSURE_MAX_SEC="${ui_heal_post_ensure_max_sec}" \
          MYRM_STACK_FRONTEND_WAIT_SEC="${MYRM_STACK_FRONTEND_WAIT_SEC:-360}" \
          bash "${SCRIPT_DIR}/lib/frontend-warmup-heal-entry.sh" || true
      else
        _heal_shared_ui_if_stale || true
      fi
      continue
    fi
    if [[ "${waited}" -eq 0 || $((waited % 10)) -eq 0 ]]; then
      echo "CHROME_E2E_WAIT: parallel attach waiting for ${errors} (${active_leases} active leases) ${waited}s remaining=${wait_sec}s (monotonic BOOTSTRAP)" >&2
    fi
    _admit_poll_touch "CHROME_E2E_ATTACH_ENDPOINT_WAIT"
    _admit_poll_budget_or_fail "CHROME_E2E_ATTACH_ENDPOINT_WAIT" || return $?
    sleep "${poll_sec}"
  done
}

_attach_parallel_wait_sec() {
  local base="${MYRM_CHROME_E2E_ATTACH_WAIT_SEC:-360}"
  local active_leases scaled
  active_leases="$(_parallel_attach_active_leases)"
  [[ "${base}" =~ ^[0-9]+$ ]] || base=360
  [[ "${active_leases}" =~ ^[0-9]+$ ]] || active_leases=0
  scaled="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from dev_gate.contract import attach_parallel_wait_sec
print(attach_parallel_wait_sec(${active_leases}, base=${base}))
")"
  [[ "${scaled}" =~ ^[0-9]+$ ]] || scaled="${base}"
  if [[ "${active_leases}" -gt 0 ]]; then
    echo "CHROME_E2E_ATTACH: parallel ADMIT scaled wait ≤${scaled}s (leases=${active_leases}; do not stop other pytest)" >&2
  fi
  echo "${scaled}"
}

_attach_epoch_pin_drop_stale_when_shared_aligned() {
  # test.sh may pin a verify-api port before shared backend heals; drop stale pin when aligned.
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_core.api_verify import resolve_e2e_api_context
from e2e_core.epoch_delivery_plane import needs_epoch_pin_backend
ctx = resolve_e2e_api_context(retry_after_apply=False)
raise SystemExit(0 if not needs_epoch_pin_backend(ctx) else 1)
" 2>/dev/null
}

_attach_epoch_pin_fast_path() {
  # P0-DGR-6: pinned verify-api must not wait monotonic shared-hot BOOTSTRAP (578s+).
  if [[ "${MYRM_E2E_EPOCH_PIN:-0}" != "1" ]]; then
    return 1
  fi
  if _attach_epoch_pin_drop_stale_when_shared_aligned; then
    echo "CHROME_E2E_ATTACH: shared epoch aligned — drop stale epoch pin api=${API_BASE}" >&2
    unset MYRM_E2E_EPOCH_PIN
    export E2E_API_BASE="${API_BASE}"
    return 1
  fi
  local runtime_py="${SCRIPT_DIR}/lib/e2e_core/runtime_identity.py"
  local pin_api="${E2E_API_BASE:-${API_BASE}}"
  local health="" waited=0 poll_sec wait_sec
  poll_sec="${MYRM_CHROME_E2E_ATTACH_POLL_SEC:-2}"
  wait_sec="${MYRM_E2E_EPOCH_PIN_ATTACH_WAIT_SEC:-90}"
  [[ "${poll_sec}" =~ ^[0-9]+$ && "${poll_sec}" -gt 0 ]] || poll_sec=2
  [[ "${wait_sec}" =~ ^[0-9]+$ && "${wait_sec}" -gt 0 ]] || wait_sec=90
  echo "CHROME_E2E_ATTACH: epoch pin fast path api=${pin_api} wait≤${wait_sec}s (skip shared-hot monotonic BOOTSTRAP)" >&2
  while [[ "${waited}" -lt "${wait_sec}" ]]; do
    if _attach_epoch_pin_drop_stale_when_shared_aligned; then
      echo "CHROME_E2E_ATTACH: shared epoch aligned during pin wait — drop stale epoch pin api=${API_BASE}" >&2
      unset MYRM_E2E_EPOCH_PIN
      export E2E_API_BASE="${API_BASE}"
      return 1
    fi
    if [[ "${pin_api}" != "${SHARED_API_BASE}" ]] \
      && ! curl -sf --max-time 3 "${pin_api%/}/api/v1/health" >/dev/null 2>&1 \
      && curl -sf --max-time 5 "${SHARED_API_BASE%/}/api/v1/health" >/dev/null 2>&1; then
      echo "CHROME_E2E_ATTACH: epoch pin early fallback to shared api=${SHARED_API_BASE} (isolated ${pin_api} not ready)" >&2
      unset MYRM_E2E_EPOCH_PIN
      export E2E_API_BASE="${SHARED_API_BASE}"
      API_BASE="${SHARED_API_BASE}"
      return 1
    fi
    if health="$("${PREFLIGHT_PY}" "${runtime_py}" \
      --auto-probe \
      --auto-hot \
      --ui "${UI_BASE}" \
      --api "${pin_api}" \
      --attach-mode \
      --require-read-attach-ready 2>&1)"; then
      echo "CHROME_E2E_READY ui=${UI_BASE} api=${pin_api} port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
      echo "${health}"
      return 0
    fi
    if [[ "${waited}" -eq 0 || $((waited % 10)) -eq 0 ]]; then
      echo "CHROME_E2E_WAIT: epoch pin attach ${waited}s remaining=$((wait_sec - waited))s" >&2
    fi
    _admit_poll_touch "CHROME_E2E_EPOCH_PIN_ATTACH"
    _admit_poll_budget_or_fail "CHROME_E2E_EPOCH_PIN_ATTACH" || return 1
    sleep "${poll_sec}"
    waited=$((waited + poll_sec))
  done
  echo "${health}" >&2
  # isolated verify-api flaked under parallel attach — fall back to shared when healthy.
  if [[ "${pin_api}" != "${SHARED_API_BASE}" ]] \
    && curl -sf --max-time 5 "${SHARED_API_BASE%/}/api/v1/health" >/dev/null 2>&1; then
    echo "CHROME_E2E_ATTACH: epoch pin fallback to shared api=${SHARED_API_BASE} (isolated ${pin_api} not ready)" >&2
    unset MYRM_E2E_EPOCH_PIN
    export E2E_API_BASE="${SHARED_API_BASE}"
    API_BASE="${SHARED_API_BASE}"
    return 1
  fi
  fail "epoch pin attach did not become ready within ${wait_sec}s — wave idle: ./myrm-dev restart --chrome; parallel: wait for drift apply (verify-api does not heal the shared API)"
}
