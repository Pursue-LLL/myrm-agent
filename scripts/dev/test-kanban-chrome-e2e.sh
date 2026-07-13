#!/usr/bin/env bash
# Kanban Chrome E2E — GLOBAL_WRITE lease, resource ledger, and UI hold window.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER="${ROOT}/myrm-agent-server"
WAVE_RESOURCE_LEASE="${ROOT}/scripts/dev/wave-resource-lease.sh"

if [[ -f "${SERVER}/.env.test" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${SERVER}/.env.test"
  set +a
fi

export MYRM_WAVE_AGENT_ID="${MYRM_WAVE_AGENT_ID:-kanban-e2e:$$}"
export WAVE_LEDGER_NAMESPACE="${WAVE_LEDGER_NAMESPACE:-kanban-e2e-$$}"
WAVE_LEDGER_LEASE_ID="$(bash "${WAVE_RESOURCE_LEASE}" acquire "${WAVE_LEDGER_NAMESPACE}" GLOBAL_WRITE)"
export WAVE_LEDGER_LEASE_ID
trap 'bash "${WAVE_RESOURCE_LEASE}" release "${WAVE_LEDGER_LEASE_ID}"' EXIT

export E2E_HOLD_MS="${E2E_HOLD_MS:-90000}"
bun "${ROOT}/scripts/dev/kanban-chrome-e2e-prepare.mjs"
