#!/usr/bin/env bash
# Stable Instinct Inbox E2E: API layer (pytest) + UI layer (Playwright).
# Prerequisite: backend on :8080 (./myrm dev). Frontend on :3000 optional for UI test.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "==> [1/2] API integration (no browser)"
cd myrm-agent-server
uv run pytest tests/api/skills/test_drafts_e2e.py -n 0 -q

echo "==> [2/2] UI E2E (Playwright, reuses running dev server)"
if ! curl -sf --max-time 5 http://localhost:3000/ >/dev/null; then
  echo "WARN: frontend :3000 not reachable — skip UI layer. Start with: cd myrm-agent-frontend && bun run dev"
  exit 0
fi

echo "==> Seeding mock drafts via HTTP (same process as backend, no SQLite lock)"
curl -sf --max-time 10 -X POST "http://127.0.0.1:8080/api/v1/skills/drafts/test/seed-mock" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Seeded:', d.get('skill_names', d))"

cd "$ROOT/myrm-agent-frontend"
if ! bunx playwright --version >/dev/null 2>&1; then
  echo "WARN: playwright not ready"
  exit 1
fi
PLAYWRIGHT_SKIP_WEBSERVER=1 \
PLAYWRIGHT_RUN_INSTINCT_INBOX_E2E=1 \
  bunx playwright test tests/e2e/instinct-inbox.spec.ts --reporter=line

echo "==> All Instinct Inbox E2E checks passed."
