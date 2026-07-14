#!/usr/bin/env bash
# Acquire/release a stable-owner resource lease for E2E scripts.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WAVE="${SCRIPT_DIR}/wave.sh"
# shellcheck source=lib/wave-lease-owner.sh
source "${SCRIPT_DIR}/lib/wave-lease-owner.sh"

case "${1:-}" in
  acquire)
    namespace="${2:-}"
    [[ -n "${namespace}" ]] || {
      echo "Usage: wave-resource-lease.sh acquire <namespace> [lane]" >&2
      exit 1
    }
    _wave_acquire_owned_lease \
      "${WAVE}" \
      "myrm-e2e-resource" \
      "${3:-${MYRM_WAVE_RESOURCE_LANE:-RESOURCE_WRITE}}" \
      "${namespace}"
    ;;
  release) _wave_release_owned_lease "${WAVE}" "myrm-e2e-resource" "${2:-}" ;;
  *)
    echo "Usage: wave-resource-lease.sh acquire <namespace> [lane]|release <leaseId>" >&2
    exit 1
    ;;
esac
