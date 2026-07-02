#!/usr/bin/env bash
# Instinct Inbox E2E: API layer only (pytest). WebUI 阶段用 MCP chrome-devtools（真实 Chrome :3000），禁止 @playwright/test。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

echo "==> API integration (no headless browser)"
cd myrm-agent-server
uv run pytest tests/api/skills/test_drafts_e2e.py -n 0 -q -m e2e

echo "==> Seeding mock drafts via HTTP"
curl -sf --max-time 10 -X POST "http://127.0.0.1:8080/api/v1/skills/drafts/test/seed-mock" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('Seeded:', d.get('skill_names', d))"

if curl -sf --max-time 5 http://localhost:3000/ >/dev/null; then
  echo "==> Frontend :3000 reachable — UI 验收请用 MCP chrome-devtools（已登录 Chrome），禁止 Playwright 无头浏览器"
else
  echo "WARN: frontend :3000 not reachable — API layer passed. UI: cd myrm-agent-frontend && bun run dev, then MCP chrome-devtools"
fi

echo "==> Instinct Inbox API E2E passed."
