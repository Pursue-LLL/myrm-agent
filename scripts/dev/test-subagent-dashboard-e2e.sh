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

cd "$FRONTEND"
bunx playwright test tests/e2e/subagent-dashboard.spec.ts --reporter=line --workers=1
