#!/usr/bin/env bun
/**
 * [POS] P2c verify — after UI cancel, subagent must not be in ACTIVE_SUBAGENTS (cancel → 404).
 * Usage: bun scripts/dev/subagent-dashboard-e2e-verify.mjs <chatId> <taskId>
 */

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? process.env.E2E_API_BASE ?? 'http://127.0.0.1:8080';
const chatId = process.argv[2];
const taskId = process.argv[3];

if (!chatId || !taskId) {
  console.error('Usage: subagent-dashboard-e2e-verify.mjs <chatId> <taskId>');
  process.exit(1);
}

const res = await fetch(`${apiBase}/api/v1/chats/${chatId}/subagents/${taskId}/cancel`, {
  method: 'POST',
});
if (res.status === 404) {
  console.log(JSON.stringify({ ok: true, reason: 'not_running' }));
  process.exit(0);
}
console.error(JSON.stringify({ ok: false, status: res.status, body: await res.json().catch(() => ({})) }));
process.exit(1);
