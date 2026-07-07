#!/usr/bin/env bun
/**
 * [POS] channel_notify_tool — live API prepare (agent-stream + chat delivery).
 * [OUTPUT] stdout JSON: { ok, chatId, notifySteps, deliveredMessage, uiUrl }
 * WebUI verification: MCP chrome-devtools on logged-in Chrome :3000 (not isolatedContext).
 */

import { randomUUID } from 'node:crypto';
import { apiBase, apiFetch, ensureLoggedIn } from './subagent-dashboard-e2e-auth.mjs';

const DEFAULT_AGENT_ID = 'be4e86d3-6b36-4b3c-bed0-a1932103a7a4';
const DEFAULT_RECIPIENT_CHAT_ID = 'e2e-test-recipient-001';
const NOTIFY_BODY = 'E2E integration test';

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

function invokedToolNames(events) {
  const names = new Set();
  for (const event of events) {
    if (!event || typeof event !== 'object') {
      continue;
    }
    if (!['tasks_steps', 'tool_start', 'tool_end'].includes(event.type)) {
      continue;
    }
    if (typeof event.tool_name === 'string' && event.tool_name) {
      names.add(event.tool_name);
    }
  }
  return names;
}

async function collectAgentStream(payload) {
  const res = await apiFetch('/api/v1/agents/agent-stream', {
    method: 'POST',
    headers: { Accept: 'text/event-stream' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`agent-stream ${res.status}: ${text.slice(0, 800)}`);
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

async function fetchRecipientMessages(recipientChatId) {
  const res = await apiFetch(`/api/v1/chats/${recipientChatId}/messages`);
  if (!res.ok) {
    return [];
  }
  const body = await res.json();
  const page = body?.data;
  if (page && Array.isArray(page.messages)) {
    return page.messages;
  }
  if (Array.isArray(page)) {
    return page;
  }
  return [];
}

async function main() {
  await ensureLoggedIn();

  const useLite = process.env.NOTIFY_E2E_USE_LITE === '1';
  const rawModel = useLite ? requireEnv('LITE_MODEL') : requireEnv('BASIC_MODEL');
  const model = stripProviderPrefix(rawModel);
  const providerId = inferProviderId(rawModel);
  const agentId = process.env.NOTIFY_E2E_AGENT_ID ?? DEFAULT_AGENT_ID;
  const recipientChatId = process.env.NOTIFY_E2E_RECIPIENT_CHAT_ID ?? DEFAULT_RECIPIENT_CHAT_ID;
  const chatId = `e2e_notify_${randomUUID().slice(0, 8)}`;

  await apiFetch('/api/v1/chats/', {
    method: 'POST',
    body: JSON.stringify({ chat_id: chatId }),
  });

  const query = [
    'Call channel_notify_tool exactly once.',
    `Send body "${NOTIFY_BODY}" to the configured chat target (channel chat).`,
    'Do not call any other tools.',
    'After the tool succeeds, reply exactly NOTIFY_DONE.',
  ].join(' ');

  const payload = {
    message_id: `msg_${randomUUID().slice(0, 8)}`,
    chat_id: chatId,
    query,
    action_mode: 'agent',
    agent_id: agentId,
    model_selection: {
      providerId,
      model,
    },
    enable_memory: false,
    timezone: 'UTC',
  };

  const events = await collectAgentStream(payload);
  const invoked = invokedToolNames(events);
  const notifySteps = events.filter(
    (event) => event?.type === 'tasks_steps' && event?.tool_name === 'channel_notify_tool',
  );
  const messages = await fetchRecipientMessages(recipientChatId);
  const deliveredMessage = messages.find(
    (msg) =>
      typeof msg?.content === 'string' &&
      msg.content.includes(NOTIFY_BODY),
  );

  const topLevelError = events.find((event) => event?.type === 'error');
  const ok =
    invoked.has('channel_notify_tool') &&
    notifySteps.length > 0 &&
    Boolean(deliveredMessage) &&
    !topLevelError;

  const result = {
    ok,
    apiBase,
    agentId,
    recipientChatId,
    chatId,
    model: { providerId, model },
    invokedTools: [...invoked],
    notifyStepCount: notifySteps.length,
    deliveredMessage: deliveredMessage
      ? { id: deliveredMessage.id, content: deliveredMessage.content?.slice(0, 200) }
      : null,
    topLevelError: topLevelError ?? null,
    uiUrl: `${process.env.E2E_UI_BASE ?? 'http://127.0.0.1:3000'}/?agent_id=${agentId}`,
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
