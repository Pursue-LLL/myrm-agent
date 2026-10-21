#!/usr/bin/env bash
# Acquire/release an access-scoped lease for ./myrm test -m chrome_e2e.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WAVE="${SCRIPT_DIR}/wave.sh"
# shellcheck source=lib/wave-lease-owner.sh
source "${SCRIPT_DIR}/lib/wave-lease-owner.sh"

case "${1:-}" in
  acquire)
    case "${MYRM_E2E_ACCESS_SCOPE:-}" in
      READ) lane="READ" ;;
      NAMESPACE_WRITE) lane="RESOURCE_WRITE" ;;
      GLOBAL_WRITE) lane="GLOBAL_WRITE" ;;
      *)
        echo "E2E_ACCESS_SCOPE_INVALID: expected READ, NAMESPACE_WRITE, or GLOBAL_WRITE" >&2
        exit 2
        ;;
    esac
    namespace=""
    if [[ "${MYRM_PRIVATE_BACKEND:-0}" == "1" ]]; then
      # PRIVATE sessions have an isolated backend. Persist that identity on
      # every wave lease so shared-stack gates can ignore private work while
      # retaining ownership, heartbeat, and cleanup semantics.
      namespace="${MYRM_E2E_LEASE_NAMESPACE:-e2e:private:${MYRM_E2E_RUN_ID:-}}"
      [[ -n "${namespace}" ]] || {
        echo "E2E_PRIVATE_NAMESPACE_REQUIRED: PRIVATE E2E needs MYRM_E2E_RUN_ID" >&2
        exit 2
      }
    elif [[ "${lane}" == "RESOURCE_WRITE" ]]; then
      namespace="${MYRM_E2E_NAMESPACE:-${MYRM_E2E_RUN_ID:-}}"
      [[ -n "${namespace}" ]] || {
        echo "E2E_NAMESPACE_REQUIRED: ./myrm test must provide MYRM_E2E_NAMESPACE" >&2
        exit 2
      }
    fi
    _wave_acquire_owned_lease_with_wait "${WAVE}" "myrm-test-e2e" "${lane}" "${namespace}"
    ;;
  release) _wave_release_owned_lease_and_close_if_idle "${WAVE}" "myrm-test-e2e" "${2:-}" ;;
  *)
    echo "Usage: wave-e2e-lease.sh acquire|release <leaseId>" >&2
    exit 1
    ;;
esac
