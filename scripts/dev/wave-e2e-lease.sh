#!/usr/bin/env bash
# Acquire/release LIVE_AGENT lease for ./myrm test -m e2e (replaces api-e2e.lock).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WAVE="${SCRIPT_DIR}/wave.sh"
AGENT_ID="${MYRM_WAVE_AGENT_ID:-myrm-test-e2e:$$}"

_acquire() {
  local status_json wave_open
  status_json="$(bash "${WAVE}" status 2>/dev/null || true)"
  wave_open=0
  if [[ "${status_json}" == *'"status": "open"'* ]]; then
    wave_open=1
  fi
  if [[ "${wave_open}" -eq 0 ]]; then
    bash "${WAVE}" --agent "${AGENT_ID}" open >/dev/null
  fi
  bash "${WAVE}" --agent "${AGENT_ID}" lease acquire LIVE_AGENT | python3 -c "
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
  acquire) _acquire ;;
  release) _release "${2:-}" ;;
  *)
    echo "Usage: wave-e2e-lease.sh acquire|release <leaseId>" >&2
    exit 1
    ;;
esac
