#!/usr/bin/env bash
# Attach fast path: auth-template repair, then what a parallel agent runs once the shared stack and Chrome
# are up (data plane check, mux heal without restarting a healthy one, ws stamp, health verify).
# Sourced by chrome-e2e-preflight.sh, which owns every global read here; this file only defines functions.
# shellcheck shell=bash

_maybe_reseal_auth_template_after_attach() {
  PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
    "${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_core.auth_provisioner import reseal_auth_template_for_current_runtime
from e2e_core.api_verify import workspace_backend_fingerprint
origin = '${UI_BASE}'
ws = workspace_backend_fingerprint()
status = reseal_auth_template_for_current_runtime(origin=origin, workspace_fingerprint=ws)
line = (
    f'CHROME_E2E_AUTH_RESEAL: status={status[\"status\"]} '
    f'next={status[\"next_action\"]} runtime_fp={status.get(\"runtimeFingerprint\", \"\")}'
)
try:
    print(line, file=sys.stderr, flush=True)
except BrokenPipeError:
    pass
" 2>/dev/null || true
}

_prepare_auth_template_before_attach() {
  local attempt=1
  local max_attempts="${MYRM_AUTH_PREPARE_ATTEMPTS:-3}"
  local backoff_sec="${MYRM_AUTH_PREPARE_BACKOFF_SEC:-3}"
  local lock_wait_sec="${MYRM_AUTH_PREPARE_LOCK_WAIT_SEC:-15}"
  while :; do
    if PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
      "${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_core.auth_provisioner import prepare_auth_template_for_attach
from e2e_core.api_verify import workspace_backend_fingerprint
origin = '${UI_BASE}'
status = prepare_auth_template_for_attach(
    origin=origin,
    workspace_fingerprint=workspace_backend_fingerprint(),
    lock_wait_sec=float('${lock_wait_sec}'),
)
line = (
    f'CHROME_E2E_AUTH_PREPARE: status={status[\"status\"]} '
    f'next={status[\"next_action\"]} runtime_fp={status.get(\"runtimeFingerprint\", \"\")}'
)
try:
    print(line, file=sys.stderr, flush=True)
except BrokenPipeError:
    pass
if status['next_action'] not in {'READY', 'AUTH_SETUP_REQUIRED'}:
    raise SystemExit('AUTH_TEMPLATE_PREPARE_UNAVAILABLE')
"; then
      return 0
    fi
    if [[ "${attempt}" -ge "${max_attempts}" ]]; then
      fail "auth template preparation failed before attach"
    fi
    echo "CHROME_E2E_AUTH_PREPARE_RETRY: attempt=${attempt}/${max_attempts} backoff=${backoff_sec}s" >&2
    attempt=$((attempt + 1))
    sleep "${backoff_sec}"
  done
}

_attach_fast_path() {
  if _attach_epoch_pin_fast_path; then
    return 0
  fi
  local runtime_py="${SCRIPT_DIR}/lib/e2e_core/runtime_identity.py"
  local health="" waited=0 ui_heal_during_wait=0 mux_heal_during_wait=0
  local wait_sec poll_sec active_leases errors require_ready
  # launch-force + skip attach wait — match solo PASS (46138): dev servers + CDP verified
  # above; do not burn 590s hot-pool BOOTSTRAP (shellHot=false acceptable under attach).
  if [[ "${MYRM_E2E_LAUNCH_FORCE:-}" == "1" && "${MYRM_PREFLIGHT_SKIP_ATTACH_WAIT:-}" == "1" ]] \
    && myrm_chrome_e2e_cdp_healthy; then
    health="$("${PREFLIGHT_PY}" "${runtime_py}" \
      --auto-probe \
      --auto-hot \
      --ui "${UI_BASE}" \
      --api "${API_BASE}" \
      --attach-mode 2>&1)" || health=""
    echo "CHROME_E2E_ATTACH: launch-force fast path (CDP live; defer hot-pool gate)" >&2
    echo "CHROME_E2E_READY ui=${UI_BASE} api=${API_BASE} port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
    echo "${health}"
    _maybe_reseal_auth_template_after_attach
    return 0
  fi
  _ensure_plane_before_attach
  require_ready="$(_attach_health_require_args)"
  poll_sec="${MYRM_CHROME_E2E_ATTACH_POLL_SEC:-2}"
  active_leases="$(_parallel_attach_active_leases)"
  [[ "${poll_sec}" =~ ^[0-9]+$ && "${poll_sec}" -gt 0 ]] || poll_sec=2
  _bootstrap_attach_begin "${active_leases}"
  wait_sec="$(_bootstrap_attach_remaining_sec)"
  if [[ "${require_ready}" == "--require-read-attach-ready" ]]; then
    echo "CHROME_E2E_ATTACH: READ lane stack-core attach uses monotonic BOOTSTRAP remaining=${wait_sec}s (no independent 150s gate)" >&2
  fi
  if [[ "${wait_sec}" -le 0 ]]; then
    fail "BOOTSTRAP attach budget exhausted before stack-core gate — do not stop other pytest; run ./myrm-dev e2e-context"
  fi
  local wait_started=$SECONDS drift_cap=0
  drift_cap="$(_epoch_drift_shared_attach_cap_sec "${active_leases}")"
  [[ "${drift_cap}" =~ ^[0-9]+$ ]] || drift_cap=0
  if [[ "${drift_cap}" -gt 0 ]]; then
    echo "CHROME_E2E_ATTACH: epoch drift SHARED attach cap=${drift_cap}s (parallel lease aware; monotonic BOOTSTRAP may be higher)" >&2
  fi
  _attach_drift_cap_exceeded() {
    [[ "${drift_cap}" -gt 0 ]] || return 1
    local admit_elapsed
    admit_elapsed="$(
      PYTHONPATH="${SCRIPT_DIR}/lib:${PYTHONPATH:-}" \
        "${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_session_runtime.lifecycle import elapsed_wall_sec
print(int(elapsed_wall_sec()))
" 2>/dev/null || echo 0
    )"
    [[ "${admit_elapsed}" =~ ^[0-9]+$ ]] || admit_elapsed=0
    [[ "${admit_elapsed}" -ge "${drift_cap}" || "${waited}" -ge "${drift_cap}" ]]
  }
  _attach_drift_cap_fail_msg() {
    if [[ "${active_leases}" -gt 0 ]]; then
      echo "epoch drift attach cap ${drift_cap}s exceeded (${active_leases} active leases defer shared reload) — keep this session; retry attach after leases drain; do not stop other pytest"
    else
      echo "epoch drift attach cap ${drift_cap}s exceeded with no active leases — run ./myrm-dev restart --chrome when wave idle (plane STALE/mux=0: verify-api does not heal shared or mux); do not stop other pytest"
    fi
  }
  if _attach_drift_cap_exceeded; then
    echo "${health}" >&2
    fail "$(_attach_drift_cap_fail_msg)"
  fi
  while true; do
    wait_sec="$(_bootstrap_attach_remaining_sec)"
    if _attach_drift_cap_exceeded; then
      echo "${health}" >&2
      fail "$(_attach_drift_cap_fail_msg)"
    fi
    if [[ "${wait_sec}" -le 0 ]]; then
      echo "${health}" >&2
      fail "parallel attach health snapshot did not recover within monotonic BOOTSTRAP budget — wait for shared hot recovery; do not stop other pytest; solo warmup: ./myrm-dev ready --chrome"
    fi
    if health="$("${PREFLIGHT_PY}" "${runtime_py}" \
      --auto-probe \
      --auto-hot \
      --ui "${UI_BASE}" \
      --api "${API_BASE}" \
      --attach-mode \
      "${require_ready}" 2>&1)"; then
      echo "CHROME_E2E_READY ui=${UI_BASE} api=${API_BASE} port=${MYRM_CHROME_E2E_PORT} profile=${MYRM_CHROME_E2E_DATA_DIR}"
      echo "${health}"
      _maybe_reseal_auth_template_after_attach
      return 0
    fi
    errors="$("${PREFLIGHT_PY}" -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from e2e_core.endpoint_health import attach_endpoint_errors
print(', '.join(attach_endpoint_errors('${UI_BASE}', '${API_BASE}')))
")"
    if [[ "${errors}" == *"ui=half_dead"* || "${errors}" == *"ui=unreachable"* ]] \
      && [[ "${active_leases}" -le 0 ]] \
      && [[ "${waited}" -ge 30 ]] \
      && [[ $((waited % 30)) -eq 0 ]] \
      && [[ "${ui_heal_during_wait}" -lt 2 ]]; then
      ui_heal_during_wait=$((ui_heal_during_wait + 1))
      echo "CHROME_E2E_ATTACH_HEAL: ui stale during shared_hot wait — bounded frontend heal ${ui_heal_during_wait}/2" >&2
      _heal_shared_ui_if_stale || true
      continue
    fi
    if [[ "${health}" == *"shellHot=false"* || "${health}" == *"clientHot=false"* ]] \
      && [[ "${require_ready}" == "--require-attach-ready" ]] \
      && [[ "${waited}" -ge 60 ]] \
      && [[ $((waited % 60)) -eq 0 ]] \
      && [[ "${mux_heal_during_wait}" -lt 2 ]]; then
      mux_heal_during_wait=$((mux_heal_during_wait + 1))
      echo "CHROME_E2E_ATTACH_HEAL: mux heal during shared_hot wait ${mux_heal_during_wait}/2" >&2
      _heal_mux_request_timeout_drift || true
      _heal_mux_under_parallel_attach_load || true
      continue
    fi
    if [[ "${mux_heal_during_wait}" -lt 2 ]] \
      && [[ "${health}" == *"wsStampMatch=false"* ]] \
      && _mux_upstream_ready; then
      if [[ "${MYRM_CHROME_E2E_ATTACH}" == "1" ]] && _mux_solo_gate_cluster_clear; then
        mux_heal_during_wait=$((mux_heal_during_wait + 1))
        echo "CHROME_E2E_ATTACH_HEAL: solo ws restamp during attach wait ${mux_heal_during_wait}/2" >&2
        _stamp_mux_ws_url || true
        _stamp_mux_daemon_ws_url || true
        continue
      fi
    fi
    wait_sec="$(_bootstrap_attach_remaining_sec)"
    if [[ "${waited}" -eq 0 || $((waited % 10)) -eq 0 ]]; then
      echo "CHROME_E2E_WAIT: $(_attach_wait_label) ${waited}s remaining=${wait_sec}s (leases=${active_leases}; monotonic BOOTSTRAP)" >&2
    fi
    _admit_poll_touch "CHROME_E2E_ATTACH_SHARED_HOT_WAIT"
    _admit_poll_budget_or_fail "CHROME_E2E_ATTACH_SHARED_HOT_WAIT" || return $?
    sleep "${poll_sec}"
    waited=$((SECONDS - wait_started))
  done
}
