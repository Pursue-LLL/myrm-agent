#!/usr/bin/env bash
# Acquire/release RESOURCE_WRITE lease for E2E scripts that create namespaced resources.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WAVE="${SCRIPT_DIR}/wave.sh"
AGENT_ID="${MYRM_WAVE_AGENT_ID:-myrm-e2e-resource:$$}"

_acquire() {
  local namespace="$1"
  [[ -n "${namespace}" ]] || {
    echo "Usage: wave-resource-lease.sh acquire <namespace>" >&2
    exit 1
  }
  local status_json wave_open
  status_json="$(bash "${WAVE}" status 2>/dev/null || true)"
  wave_open=0
  if [[ "${status_json}" == *'"status": "open"'* ]]; then
    wave_open=1
  fi
  if [[ "${wave_open}" -eq 0 ]]; then
    bash "${WAVE}" --agent "${AGENT_ID}" open >/dev/null
  fi
  bash "${WAVE}" --agent "${AGENT_ID}" lease acquire RESOURCE_WRITE --namespace "${namespace}" | python3 -c "
import json, sys
payload = json.load(sys.stdin)
print(payload['lease']['leaseId'])
"
}

_release() {
  local lease_id="$1"
  [[ -n "${lease_id}" ]] || return 0
  bash "${WAVE}" --agent "${AGENT_ID}" lease release "${lease_id}" >/dev/null 2>&1 || true
}

cmd="${1:-}"
case "${cmd}" in
  acquire) _acquire "${2:-}" ;;
  release) _release "${2:-}" ;;
  *)
    echo "Usage: wave-resource-lease.sh acquire <namespace>|release <leaseId>" >&2
    exit 1
    ;;
esac
