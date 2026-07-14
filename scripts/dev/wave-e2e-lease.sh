#!/usr/bin/env bash
# Acquire/release a stable-owner READ or LIVE_AGENT lease for ./myrm test -m e2e.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WAVE="${SCRIPT_DIR}/wave.sh"
# shellcheck source=lib/wave-lease-owner.sh
source "${SCRIPT_DIR}/lib/wave-lease-owner.sh"

case "${1:-}" in
  acquire)
    lane="${MYRM_E2E_LANE:-LIVE_AGENT}"
    case "${lane}" in
      READ | RESOURCE_WRITE | GLOBAL_WRITE | LIVE_AGENT) ;;
      *)
        echo "E2E_LANE_INVALID: MYRM_E2E_LANE must be READ, RESOURCE_WRITE, GLOBAL_WRITE, or LIVE_AGENT" >&2
        exit 2
        ;;
    esac
    namespace=""
    if [[ "${lane}" == "RESOURCE_WRITE" ]]; then
      namespace="${MYRM_E2E_NAMESPACE:-}"
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
