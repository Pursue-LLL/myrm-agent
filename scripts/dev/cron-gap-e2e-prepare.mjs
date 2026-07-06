#!/usr/bin/env bun
/**
 * [POS] Cron capability_gap — API prepare (agent-stream discover miss → capability_gap).
 * [OUTPUT] stdout JSON: { chatId, gapEvent, ok }
 * UI toast verification: MCP chrome-devtools on real Chrome :3000 after `bun run dev`.
 */

import { randomUUID } from 'node:crypto';
import { apiBase, apiFetch, ensureLoggedIn } from './subagent-dashboard-e2e-auth.mjs';

const gapQuery = 'schedule daily reminder cron job at 9am every morning';

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing ${name} (source myrm-agent-server/.env.test)`);
  }
  return value;
}

function inferProviderId(model) {
  if (model.includes('/')) {
    return model.split('/')[0] ?? 'minimax';
  }
  return 'minimax';
}

function stripProviderPrefix(model) {
  if (!model.includes('/')) {
    return model;
  }
  return model.split('/').slice(1).join('/');
}

async function collectAgentStream(payload) {
  const res = await apiFetch('/api/v1/agents/agent-stream', {
    method: 'POST',
    headers: { Accept: 'text/event-stream' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`agent-stream ${res.status}: ${text.slice(0, 500)}`);
  }

  const events = [];
  const reader = res.body?.getReader();
  if (!reader) {
    throw new Error('agent-stream response has no body');
  }
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed.startsWith('data: ')) {
        continue;
      }
      const raw = trimmed.slice(6);
      if (raw === '[DONE]') {
        return events;
      }
      try {
        events.push(JSON.parse(raw));
      } catch {
        // skip malformed frames
      }
    }
  }
  return events;
}

async function main() {
  await ensureLoggedIn();
  const liteModel = requireEnv('LITE_MODEL');
  const model = stripProviderPrefix(liteModel);
  const providerId = inferProviderId(liteModel);
  const chatId = `e2e_cron_gap_${randomUUID().slice(0, 8)}`;

  await apiFetch('/api/v1/chats/', {
    method: 'POST',
    body: JSON.stringify({ chat_id: chatId }),
  });

  const payload = {
    message_id: `msg_${randomUUID().slice(0, 8)}`,
    chat_id: chatId,
    query: [
      'You MUST call discover_capability_tool exactly once with query',
      `'${gapQuery}'.`,
      'Do not call any other tool.',
      'After the tool returns, reply DONE.',
    ].join(' '),
    action_mode: 'agent',
    model_selection: {
      providerId,
      model,
    },
    agent_config: {
      enabled_builtin_tools: ['web_search', 'memory'],
      skill_ids: [],
    },
    timezone: 'UTC',
  };

  const events = await collectAgentStream(payload);
  const gapEvent = events.find((event) => event?.type === 'capability_gap');
  const ok =
    gapEvent?.data?.tool_id === 'cron' ||
    JSON.stringify(events).includes('<CapabilityGap>');

  const result = {
    ok,
    chatId,
    apiBase,
    gapEvent: gapEvent ?? null,
    uiUrl: `${process.env.E2E_UI_BASE ?? 'http://127.0.0.1:3000'}/chat/${chatId}`,
  };

  console.log(JSON.stringify(result, null, 2));
  if (!ok) {
    process.exit(1);
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
