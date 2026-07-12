#!/usr/bin/env bash
# Subagent Dashboard E2E — local monorepo lane only.
#
# Local dev: requires editable harness (./myrm harness install from open-perplexity root).
# Release/CI: uses PyPI harness from uv.lock — do not run this script in CI; use API-only tests.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SERVER="$ROOT/myrm-agent-server"

if [[ -f "$SERVER/.env.test" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$SERVER/.env.test"
  set +a
fi

# shellcheck source=lib/backend_bg.sh
source "$ROOT/scripts/dev/lib/backend_bg.sh"

# Monorepo: live :8080 must import editable harness source (never hand-copy into site-packages).
_require_harness_editable_for_monorepo "${SERVER}"

if ! curl -sf --max-time 2 http://127.0.0.1:8080/api/v1/health >/dev/null; then
  echo "==> Starting backend on :8080"
  _start_backend_bg "$SERVER"
fi

echo "==> API prepare (delegate subagent; keep process alive for UI window)"
echo "==> UI phase: MCP chrome-devtools on real Chrome at :3000"
echo "    Run prepare in background with hold, open uiUrl immediately, then:"
echo "    1) Click [data-testid=subagent-dashboard-trigger]"
echo "    2) Confirm cancel on running row ([data-testid=subagent-cancel-btn])"
echo "    3) bun scripts/dev/subagent-dashboard-e2e-verify.mjs <chatId> <taskId>"
echo ""
echo "    Tip: E2E_HOLD_MS=90000 keeps prepare alive after JSON so list/cancel stay reachable."

WAVE_RESOURCE_LEASE="${ROOT}/scripts/dev/wave-resource-lease.sh"
WAVE_LEDGER_NAMESPACE="subagent-dashboard-e2e-$$"
export MYRM_WAVE_AGENT_ID="${MYRM_WAVE_AGENT_ID:-subagent-dashboard-e2e:$$}"
WAVE_LEDGER_LEASE_ID="$(bash "${WAVE_RESOURCE_LEASE}" acquire "${WAVE_LEDGER_NAMESPACE}" GLOBAL_WRITE)"
export WAVE_LEDGER_LEASE_ID
export WAVE_LEDGER_NAMESPACE
trap 'bash "${WAVE_RESOURCE_LEASE}" release "${WAVE_LEDGER_LEASE_ID}"' EXIT

export E2E_HOLD_MS="${E2E_HOLD_MS:-90000}"
bun "$ROOT/scripts/dev/subagent-dashboard-e2e-prepare.mjs"
