#!/usr/bin/env bun
/**
 * [POS] P2c verify — after UI cancel, subagent must not be in ACTIVE_SUBAGENTS (cancel → 404).
 * Usage: bun scripts/dev/subagent-dashboard-e2e-verify.mjs <chatId> <taskId>
 */

import { cancelSubagent, ensureLoggedIn } from './subagent-dashboard-e2e-auth.mjs';

const chatId = process.argv[2];
const taskId = process.argv[3];

if (!chatId || !taskId) {
  console.error('Usage: subagent-dashboard-e2e-verify.mjs <chatId> <taskId>');
  process.exit(1);
}

await ensureLoggedIn();
const res = await cancelSubagent(chatId, taskId);
if (res.status === 404) {
  console.log(JSON.stringify({ ok: true, reason: 'not_running' }));
  process.exit(0);
}
const body = await res.json().catch(() => ({}));
if (res.status === 200 && body?.data?.cancelled === true) {
  console.error(
    JSON.stringify({
      ok: false,
      reason: 'still_cancellable',
      hint: 'Run verify after UI cancel (expect 404), not after a successful REST cancel.',
    }),
  );
  process.exit(1);
}
console.error(JSON.stringify({ ok: false, status: res.status, body }));
process.exit(1);
