#!/usr/bin/env bun
/**
 * [POS] P2c Subagent Dashboard E2E — light chat scope (no subagent spawn).
 * [OUTPUT] stdout JSON: { chatId, uiUrl, apiBase }
 * Used by pure UI-injection dashboard tests (sort/stop-all/teammate/stream/
 * overtime/stale/expand/header) that seed the store bridge directly and do
 * not need a real LLM delegation.
 */

import { randomUUID } from 'node:crypto';
import { apiBase, apiFetch, ensureLoggedIn } from './subagent-dashboard-e2e-auth.mjs';

const uiBase = process.env.E2E_UI_BASE ?? 'http://127.0.0.1:3000';

async function main() {
  await ensureLoggedIn();
  const chatId = randomUUID();
  const res = await apiFetch('/api/v1/chats/', {
    method: 'POST',
    body: JSON.stringify({
      chat_id: chatId,
      title: `E2E Subagent Dashboard Light ${Date.now()}`,
      action_mode: 'agent',
      agent_id: 'builtin-general',
      messages: [],
    }),
  });
  if (!res.ok) {
    throw new Error(`seed light chat failed: ${res.status} ${(await res.text()).slice(0, 300)}`);
  }
  console.log(
    `E2E_PREPARE_JSON=${JSON.stringify({ chatId, uiUrl: `${uiBase}/${chatId}`, apiBase })}`,
  );
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
