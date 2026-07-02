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

echo "==> API prepare (delegate subagent via agent-stream)"
echo "==> UI phase: MCP chrome-devtools on real Chrome at :3000"
echo "    1) Open uiUrl from JSON below"
echo "    2) Click [data-testid=subagent-dashboard-trigger], cancel running row"
echo "    3) bun scripts/dev/subagent-dashboard-e2e-verify.mjs <chatId> <taskId>"
bun "$ROOT/scripts/dev/subagent-dashboard-e2e-prepare.mjs"
