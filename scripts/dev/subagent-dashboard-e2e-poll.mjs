#!/usr/bin/env bun
/** Poll GET /subagents immediately after prepare (debug persistence). */
import { spawnSync } from 'node:child_process';
import { ensureLoggedIn, apiFetch } from './subagent-dashboard-e2e-auth.mjs';

const out = spawnSync('bun', ['scripts/dev/subagent-dashboard-e2e-prepare.mjs'], {
  encoding: 'utf8',
  cwd: new URL('../..', import.meta.url).pathname,
  env: process.env,
});
if (out.status !== 0) {
  console.error(out.stderr || out.stdout);
  process.exit(out.status ?? 1);
}
const prep = JSON.parse(out.stdout.trim());
await ensureLoggedIn();

let lastDelay = 0;
for (const delay of [0, 500, 1000, 2000, 5000, 10000, 30000, 60000]) {
  const waitMs = delay - lastDelay;
  lastDelay = delay;
  if (waitMs > 0) {
    await new Promise((resolve) => setTimeout(resolve, waitMs));
  }
  const res = await apiFetch(`/api/v1/chats/${prep.chatId}/subagents`);
  const json = await res.json();
  const row = (json.data ?? []).find((entry) => entry?.task_id === prep.taskId);
  console.log(`+${delay}ms`, row?.status ?? 'MISSING', 'rows', (json.data ?? []).length);
}
const cancel = await apiFetch(`/api/v1/chats/${prep.chatId}/subagents/${prep.taskId}/cancel`, {
  method: 'POST',
  body: '{}',
});
console.log('cancel_status', cancel.status);
process.exit(cancel.status === 200 ? 0 : 1);
