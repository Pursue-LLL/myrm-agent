#!/usr/bin/env bash
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
if ! curl -sf --max-time 2 http://127.0.0.1:8080/api/v1/health >/dev/null; then
  echo "==> Starting backend on :8080"
  _start_backend_bg "$SERVER"
fi

echo "==> Sync harness sub_agents into server venv (session_tree + registry map)"
/bin/cp -f \
  "$ROOT/../myrm-agent-harness/src/myrm_agent_harness/agent/sub_agents/session_tree.py" \
  "$ROOT/../myrm-agent-harness/src/myrm_agent_harness/agent/sub_agents/manager.py" \
  "$ROOT/../myrm-agent-harness/src/myrm_agent_harness/agent/sub_agents/_manager_spawn.py" \
  "$SERVER/.venv/lib/python3.13/site-packages/myrm_agent_harness/agent/sub_agents/"

echo "==> API prepare (delegate subagent; keep process alive for UI window)"
echo "==> UI phase: MCP chrome-devtools on real Chrome at :3000"
echo "    Run prepare in background with hold, open uiUrl immediately, then:"
echo "    1) Click [data-testid=subagent-dashboard-trigger]"
echo "    2) Confirm cancel on running row ([data-testid=subagent-cancel-btn])"
echo "    3) bun scripts/dev/subagent-dashboard-e2e-verify.mjs <chatId> <taskId>"
echo ""
echo "    Tip: E2E_HOLD_MS=90000 keeps prepare alive after JSON so list/cancel stay reachable."

export E2E_HOLD_MS="${E2E_HOLD_MS:-90000}"
bun "$ROOT/scripts/dev/subagent-dashboard-e2e-prepare.mjs"
