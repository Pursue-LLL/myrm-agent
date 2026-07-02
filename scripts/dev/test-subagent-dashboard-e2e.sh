#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
FRONTEND="$ROOT/myrm-agent-frontend"
SERVER="$ROOT/myrm-agent-server"

if [[ -f "$SERVER/.env.test" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$SERVER/.env.test"
  set +a
fi

export PLAYWRIGHT_SKIP_WEBSERVER="${PLAYWRIGHT_SKIP_WEBSERVER:-1}"
export PLAYWRIGHT_RUN_SUBAGENT_DASHBOARD_E2E=1

# shellcheck source=lib/backend_bg.sh
source "$ROOT/scripts/dev/lib/backend_bg.sh"
if ! curl -sf --max-time 2 http://127.0.0.1:8080/api/v1/health >/dev/null; then
  echo "==> Starting backend on :8080"
  _start_backend_bg "$SERVER"
fi

cd "$FRONTEND"
bunx playwright test tests/e2e/subagent-dashboard.spec.ts --reporter=line --workers=1
