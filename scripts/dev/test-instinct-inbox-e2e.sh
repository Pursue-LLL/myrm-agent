#!/usr/bin/env bash
# Instinct Inbox E2E: API layer only (pytest). WebUI 阶段用 MCP chrome-devtools（真实 Chrome :3000），禁止 @playwright/test。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
MONOREPO_ROOT="$(cd "${ROOT}/.." && pwd)"
TEST_SH="${MONOREPO_ROOT}/scripts/dev/test.sh"

if [[ ! -x "${TEST_SH}" ]]; then
  echo "ERROR: monorepo test gate missing at ${TEST_SH} — run from open-perplexity root" >&2
  exit 1
fi

echo "==> API integration (no headless browser)"
bash "${TEST_SH}" -n0 -q -m e2e tests/api/skills/test_drafts_e2e.py

echo "==> Seeding mock drafts via HTTP"
curl -sf --max-time 10 -X POST "http://127.0.0.1:8080/api/v1/skills/drafts/test/seed-mock" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Seeded:', d.get('skill_names', d))"

if curl -sf --max-time 5 http://127.0.0.1:3000/ >/dev/null; then
  echo "==> Frontend :3000 reachable — UI 验收请用 ./myrm ready --chrome + MCP chrome-devtools"
else
  echo "WARN: frontend :3000 not reachable — API layer passed. Run: cd open-perplexity && ./myrm ready"
fi

echo "==> Instinct Inbox API E2E passed."
