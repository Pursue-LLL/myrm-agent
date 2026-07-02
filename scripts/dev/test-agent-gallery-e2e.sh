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
export PLAYWRIGHT_RUN_GALLERY_SMOKE=1

# shellcheck source=lib/backend_bg.sh
source "$ROOT/scripts/dev/lib/backend_bg.sh"
if ! curl -sf --max-time 2 http://127.0.0.1:8080/api/v1/health >/dev/null; then
  echo "==> Starting backend on :8080"
  _start_backend_bg "$SERVER"
fi

for _ in $(seq 1 30); do
  if curl -sf --max-time 2 http://127.0.0.1:8080/api/v1/health >/dev/null; then
    break
  fi
  sleep 1
done
if ! curl -sf --max-time 2 http://127.0.0.1:8080/api/v1/health >/dev/null; then
  echo "ERROR: backend :8080 not healthy" >&2
  exit 1
fi

if ! curl -sf --max-time 2 -o /dev/null http://127.0.0.1:3000/; then
  echo "ERROR: frontend :3000 not reachable — run: cd myrm-agent-frontend && bun run dev" >&2
  exit 1
fi

sleep 2
cd "$FRONTEND"
bunx playwright test tests/e2e/agent-gallery-builtin-tools-smoke.spec.ts --reporter=line --workers=1
