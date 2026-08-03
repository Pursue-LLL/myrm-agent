#!/usr/bin/env bash
# Stack mutation policy shell helpers — SSOT for attach/supervisor drift heal.
set -euo pipefail

_smp_policy_py() {
  local lib_dir="${1:-}"
  if [[ -z "${lib_dir}" ]]; then
    lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  fi
  printf '%s/stack_mutation_policy.py' "${lib_dir}"
}

_smp_state_dir() {
  printf '%s' "${MYRM_DEV_STATE_DIR:-${HOME}/.local/state/myrm-dev}"
}

_smp_apply_backend_drift_ensure() {
  local dev_stack="${1:?}" policy_py="${2:?}" state_dir="${3:?}"
  local attempt max_attempts backoff_sec flock_wait_sec
  max_attempts="${MYRM_E2E_ATTACH_BACKEND_ENSURE_MAX_ATTEMPTS:-3}"
  [[ "${max_attempts}" =~ ^[0-9]+$ && "${max_attempts}" -gt 0 ]] || max_attempts=3
  flock_wait_sec="${MYRM_E2E_CRASH_HEAL_FLOCK_WAIT_SEC:-180}"
  for attempt in $(seq 1 "${max_attempts}"); do
    if _smp_with_backend_heal_flock "${flock_wait_sec}" \
      env MYRM_WAVE_GATE_BYPASS=1 bash "${dev_stack}" backend-only ensure; then
      python3 "${policy_py}" clear-pending --state-dir "${state_dir}" >/dev/null 2>&1 || true
      return 0
    fi
    # backend-only ensure can return early while shared api is still converging;
    # treat immediate post-failure recovery as success to avoid false fail-fast.
    if _smp_shared_api_http_ok; then
      echo "CHROME_E2E_ATTACH_HEAL: backend drift ensure failed but api recovered (attempt ${attempt}/${max_attempts})" >&2
      python3 "${policy_py}" clear-pending --state-dir "${state_dir}" >/dev/null 2>&1 || true
      return 0
    fi
    if [[ "${attempt}" -lt "${max_attempts}" ]]; then
      echo "CHROME_E2E_ATTACH_HEAL: backend drift ensure retry ${attempt}/${max_attempts}" >&2
      backoff_sec=$((attempt * 3))
      sleep "${backoff_sec}"
    fi
  done
  echo "CHROME_E2E_FAIL: attach backend drift ensure failed" >&2
  return 1
}

_smp_apply_pending_drift_if_idle() {
  local monorepo_root="${1:?}" server_dir="${2:?}" dev_stack="${3:?}"
  local stack_epoch_lib policy_py state_dir active_leases
  stack_epoch_lib="$(dirname "${dev_stack}")/lib/stack-epoch.sh"
  policy_py="$(_smp_policy_py "$(dirname "${stack_epoch_lib}")")"
  state_dir="$(_smp_state_dir)"
  # shellcheck source=stack-epoch.sh
  source "${stack_epoch_lib}"
  active_leases="$(_wave_active_lease_count "${monorepo_root}")"
  if [[ "${active_leases}" != "0" ]]; then
    return 0
  fi
  if ! python3 "${policy_py}" pending-exists --state-dir "${state_dir}" | grep -q '^1$'; then
    return 0
  fi
  echo "CHROME_E2E_ATTACH_HEAL: apply pending stack drift (0 active wave leases)" >&2
  _smp_apply_backend_drift_ensure "${dev_stack}" "${policy_py}" "${state_dir}"
}

_smp_shared_api_http_ok() {
  curl -sf --max-time 5 "http://127.0.0.1:8080/api/v1/health" >/dev/null 2>&1
}

_smp_run_backend_crash_ensure() {
  local dev_stack="${1:?}"
  MYRM_WAVE_GATE_BYPASS=1 bash "${dev_stack}" backend-only ensure >/dev/null 2>&1
}

_smp_backend_heal_flock_file() {
  echo "$(_smp_state_dir)/chrome-e2e-backend-heal.flock"
}

# R46.2: serialize backend-only ensure across parallel chrome_e2e admit/heal paths.
# Without this, concurrent crash heals fight dev-stack ensure.lock and SIGTERM each other.
_smp_with_backend_heal_flock() {
  local wait_sec="${1:-180}"
  shift
  local policy_py flock_file
  policy_py="$(_smp_policy_py "$(dirname "${BASH_SOURCE[0]}")")"
  flock_file="$(_smp_backend_heal_flock_file)"
  python3 "${policy_py}" run-heal-flocked \
    --lock-file "${flock_file}" \
    --wait-sec "${wait_sec}" \
    -- "$@"
}

_smp_attach_backend_crash_heal_inner() {
  local monorepo_root="${1:?}" dev_stack="${2:?}"
  local stack_epoch_lib active_leases attempt backoff_sec
  stack_epoch_lib="$(dirname "${dev_stack}")/lib/stack-epoch.sh"
  # shellcheck source=stack-epoch.sh
  source "${stack_epoch_lib}"
  active_leases="$(_wave_active_lease_count "${monorepo_root}")"
  if _smp_shared_api_http_ok; then
    return 0
  fi
  echo "CHROME_E2E_ATTACH_HEAL: shared api down — crash heal starting (${active_leases} active leases)" >&2
  for attempt in 1 2 3; do
    case "${attempt}" in
      2) backoff_sec=5 ;;
      3) backoff_sec=10 ;;
      *) backoff_sec=0 ;;
    esac
    if [[ "${backoff_sec}" -gt 0 ]]; then
      sleep "${backoff_sec}"
    fi
    echo "CHROME_E2E_ATTACH_HEAL: crash heal attempt ${attempt}/3 (${active_leases} active leases)" >&2
    if _smp_run_backend_crash_ensure "${dev_stack}" && _smp_shared_api_http_ok; then
      echo "CHROME_E2E_ATTACH_HEAL: shared api restored after crash heal (attempt ${attempt})" >&2
      return 0
    fi
    echo "CHROME_E2E_ATTACH_HEAL: crash heal attempt ${attempt}/3 failed (api still down)" >&2
  done
  echo "CHROME_E2E_FAIL: attach backend crash heal failed after 3 attempts (api still down)" >&2
  return 1
}

_smp_attach_backend_crash_heal() {
  local monorepo_root="${1:?}" dev_stack="${2:?}"
  local wait_sec="${MYRM_E2E_CRASH_HEAL_FLOCK_WAIT_SEC:-5}"
  local policy_py flock_file
  policy_py="$(_smp_policy_py "$(dirname "${BASH_SOURCE[0]}")")"
  flock_file="$(_smp_backend_heal_flock_file)"
  # R99: fcntl.flock via Python SSOT — macOS has no GNU flock(1).
  python3 "${policy_py}" attach-crash-heal \
    --monorepo-root "${monorepo_root}" \
    --dev-stack "${dev_stack}" \
    --lock-file "${flock_file}" \
    --wait-sec "${wait_sec}" \
    --shpoib "$([[ "${E2E_PROFILE_SHPOIB:-0}" == "1" ]] && echo 1 || echo 0)"
}

_smp_attach_backend_drift_heal() {
  local monorepo_root="${1:?}" server_dir="${2:?}" dev_stack="${3:?}"
  local stack_epoch_lib active_leases policy_py state_dir action
  stack_epoch_lib="$(dirname "${dev_stack}")/lib/stack-epoch.sh"
  policy_py="$(_smp_policy_py "$(dirname "${stack_epoch_lib}")")"
  state_dir="$(_smp_state_dir)"
  # shellcheck source=stack-epoch.sh
  source "${stack_epoch_lib}"
  active_leases="$(_wave_active_lease_count "${monorepo_root}")"
  if ! _shared_backend_source_drift_pending "${server_dir}"; then
    if [[ "${active_leases}" != "0" ]]; then
      echo "CHROME_E2E_ATTACH: backend source fresh (${active_leases} active wave leases)" >&2
    fi
    return 0
  fi
  action="$(python3 "${policy_py}" decide-drift \
    --active-leases "${active_leases}" \
    --drift-pending 1)"
  case "${action}" in
    defer)
      python3 "${policy_py}" record-pending \
        --state-dir "${state_dir}" \
        --reason backend_source_drift \
        --server-dir "${server_dir}" >/dev/null
      echo "CHROME_E2E_ATTACH: defer backend-only ensure (${active_leases} active wave leases)" >&2
      ;;
    apply)
      echo "CHROME_E2E_ATTACH_HEAL: backend-only ensure (source drift, no active leases)" >&2
      _smp_apply_backend_drift_ensure "${dev_stack}" "${policy_py}" "${state_dir}"
      ;;
    *)
      ;;
  esac
}

_smp_should_defer_harness_install() {
  local monorepo_root="${1:?}"
  local stack_epoch_lib active_leases policy_py
  stack_epoch_lib="${2:-$(dirname "${BASH_SOURCE[0]}")/stack-epoch.sh}"
  # shellcheck source=stack-epoch.sh
  source "${stack_epoch_lib}"
  active_leases="$(_wave_active_lease_count "${monorepo_root}")"
  policy_py="$(dirname "${BASH_SOURCE[0]}")/stack_mutation_policy.py"
  python3 -c "
import sys
sys.path.insert(0, '$(dirname "${BASH_SOURCE[0]}")')
from stack_mutation_policy import should_defer_harness_install
raise SystemExit(0 if should_defer_harness_install(${active_leases}) else 1)
" 2>/dev/null && return 0
  [[ "${active_leases}" != "0" ]]
}
