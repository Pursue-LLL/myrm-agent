#!/usr/bin/env bash
# Acquire/release a stable-owner LIVE_AGENT lease for ./myrm test -m e2e.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WAVE="${SCRIPT_DIR}/wave.sh"
# shellcheck source=lib/wave-lease-owner.sh
source "${SCRIPT_DIR}/lib/wave-lease-owner.sh"

case "${1:-}" in
  acquire) _wave_acquire_owned_lease "${WAVE}" "myrm-test-e2e" "LIVE_AGENT" ;;
  release) _wave_release_owned_lease "${WAVE}" "${2:-}" ;;
  *)
    echo "Usage: wave-e2e-lease.sh acquire|release <leaseId>" >&2
    exit 1
    ;;
esac
