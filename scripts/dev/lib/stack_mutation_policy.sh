#!/usr/bin/env bash
# Stack mutation policy shell helpers — SSOT for attach/supervisor drift heal.
set -euo pipefail

# shellcheck source=dev_state_paths.sh
source "${BASH_SOURCE[0]%/*}/dev_state_paths.sh"

_smp_policy_py() {
  local lib_dir="${1:-}"
  if [[ -z "${lib_dir}" ]]; then
    lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  fi
  printf '%s/e2e_core/stack_mutation_policy.py' "${lib_dir}"
}

_smp_state_dir() {
  dev_state_dir
}

_smp_python() {
  if [[ -n "${VENV_PY:-}" && -x "${VENV_PY}" ]]; then
    printf '%s' "${VENV_PY}"
    return 0
  fi
  if [[ -n "${MONOREPO_ROOT:-}" ]]; then
    local candidate="${MONOREPO_ROOT}/myrm-agent/myrm-agent-server/.venv/bin/python"
    if [[ -x "${candidate}" ]]; then
      printf '%s' "${candidate}"
      return 0
    fi
  fi
  printf '%s' "python3"
}

_smp_shared_api_http_ok() {
  local health_url="${API_HEALTH:-http://127.0.0.1:${MYRM_BACKEND_PORT:-${PORT:-8080}}/api/v1/health}"
  curl -sf --max-time 5 "${health_url}" >/dev/null 2>&1
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
  "$(_smp_python)" "${policy_py}" run-heal-flocked \
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
  "$(_smp_python)" "${policy_py}" attach-crash-heal \
    --monorepo-root "${monorepo_root}" \
    --dev-stack "${dev_stack}" \
    --lock-file "${flock_file}" \
    --wait-sec "${wait_sec}" \
    --shpoib "$([[ "${E2E_PROFILE_SHPOIB:-0}" == "1" ]] && echo 1 || echo 0)"
}

_smp_attach_backend_drift_heal() {
  local monorepo_root="${1:?}" server_dir="${2:?}" dev_stack="${3:?}"
  local stack_epoch_lib active_leases policy_py state_dir
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
  # Attach is about to run tests against this backend — never reload it here:
  # a drift reload kills the backend the tests are about to use (cold start
  # 45-60s) and shows up as "backend repeatedly crashing" under concurrent
  # development churn. Record the drift so an idle-time ensure (supervisor /
  # verify-api / manual ensure) applies it when no tests are in flight.
  "$(_smp_python)" "${policy_py}" record-pending \
    --state-dir "${state_dir}" \
    --reason backend_source_drift \
    --server-dir "${server_dir}" >/dev/null 2>&1 || true
  echo "CHROME_E2E_ATTACH: defer backend drift reload during attach (${active_leases} active wave leases)" >&2
}

_smp_should_defer_harness_install() {
  local monorepo_root="${1:?}"
  local stack_epoch_lib active_leases
  stack_epoch_lib="${2:-$(dirname "${BASH_SOURCE[0]}")/stack-epoch.sh}"
  # shellcheck source=stack-epoch.sh
  source "${stack_epoch_lib}"
  active_leases="$(_wave_active_lease_count "${monorepo_root}")"
  "$(_smp_python)" -c "
import sys
sys.path.insert(0, '$(dirname "${BASH_SOURCE[0]}")')
from e2e_core.stack_mutation_policy import should_defer_harness_install
raise SystemExit(0 if should_defer_harness_install(${active_leases}) else 1)
" 2>/dev/null && return 0
  [[ "${active_leases}" != "0" ]]
}
