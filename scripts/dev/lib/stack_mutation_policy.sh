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
      MYRM_WAVE_GATE_BYPASS=1 bash "${dev_stack}" backend-only ensure >/dev/null 2>&1 \
        || echo "CHROME_E2E_WARN: attach backend ensure for source drift failed" >&2
      python3 "${policy_py}" clear-pending --state-dir "${state_dir}" >/dev/null 2>&1 || true
      ;;
    *)
      ;;
  esac
}

_smp_should_defer_harness_install() {
  local monorepo_root="${1:?}"
  local stack_epoch_lib active_leases
  stack_epoch_lib="${2:-$(dirname "${BASH_SOURCE[0]}")/stack-epoch.sh}"
  # shellcheck source=stack-epoch.sh
  source "${stack_epoch_lib}"
  active_leases="$(_wave_active_lease_count "${monorepo_root}")"
  [[ "${active_leases}" != "0" ]]
}
