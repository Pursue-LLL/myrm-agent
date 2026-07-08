#!/usr/bin/env bun
/** One-shot Live E2E: delegate browser subagent → example.com snapshot. */

import { randomUUID } from 'node:crypto';
import { apiBase, apiFetch, authCookieHeader, ensureLoggedIn } from './subagent-dashboard-e2e-auth.mjs';

const TIMEOUT_MS = Number(process.env.E2E_TIMEOUT_MS ?? 240_000);
const deviceId = process.env.E2E_CONFIG_DEVICE_ID ?? 'tauri-local';

const BROWSER_QUERY =
  "请使用 delegate_task_tool 工具委派 browser 子智能体：agent_type 必须为 'browser'，wait 设为 true，任务为打开 https://example.com 并用 browser_snapshot_tool 抓取页面，在返回结果中说明 snapshot 是否包含 'Example Domain'。必须使用原生 Function Calling，禁止在文本中伪造工具调用。";

function requireEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}

function inferProviderId(model) {
  return model.includes('/') ? (model.split('/')[0] ?? 'minimax') : 'minimax';
}

function stripProviderPrefix(model) {
  return model.includes('/') ? model.split('/').slice(1).join('/') : model;
}

async function putConfig(configKey, value) {
  const res = await apiFetch(`/api/v1/config/${configKey}`, {
    method: 'PUT',
    body: JSON.stringify({ value, deviceId }),
  });
  if (!res.ok) throw new Error(`PUT /config/${configKey}: ${await res.text()}`);
}

async function seedProviders() {
  const basicModel = requireEnv('BASIC_MODEL');
  const basicKey = requireEnv('BASIC_API_KEY');
  const basicUrl = process.env.BASIC_BASE_URL;
  const providerId = inferProviderId(basicModel);
  const modelId = stripProviderPrefix(basicModel);
  await putConfig('providers', {
    providers: [
      {
        id: providerId,
        name: providerId,
        routingProfile: providerId,
        isBuiltIn: providerId === 'minimax',
        isEnabled: true,
        apiUrl: basicUrl?.trim() || 'https://api.minimaxi.com/v1',
        apiKeys: [{ key: basicKey, isActive: true }],
        enabledModels: [modelId],
        availableModels: [modelId],
        providerType: providerId === 'minimax' ? 'minimax' : 'openai',
      },
    ],
    defaultModelConfig: {
      baseModel: { primary: { providerId, model: modelId }, fallback: null, temperature: 0.7, modelKwargs: {} },
      liteModel: { primary: null, fallback: null },
      fastModeModel: null,
      routingConfig: null,
      visionFallbackModel: null,
    },
    customModelInfo: {},
  });
}

function consumeSseBuffer(buffer) {
  const lines = buffer.split('\n');
  const remainder = lines.pop() ?? '';
  const events = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('data: ')) continue;
    try {
      events.push(JSON.parse(trimmed.slice(6)));
    } catch {
      /* ignore */
    }
  }
  return { events, remainder };
}

function eventText(event) {
  return JSON.stringify(event ?? {});
}

async function runStream(chatId, messageId) {
  const basicModel = requireEnv('BASIC_MODEL');
  const providerId = inferProviderId(basicModel);
  const modelId = stripProviderPrefix(basicModel);
  const payload = {
    query: BROWSER_QUERY,
    messageId,
    chatId,
    agentId: 'builtin-general',
    actionMode: 'general',
    agentConfig: {
      enabledBuiltinTools: ['web_search', 'browser', 'file_ops', 'code_execute'],
      browserSource: 'launch',
    },
    modelSelection: {
      providerId,
      model: modelId,
      baseUrl: process.env.BASIC_BASE_URL,
    },
  };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort('timeout'), TIMEOUT_MS);
  const allEvents = [];

  try {
    const response = await fetch(`${apiBase}/api/v1/agents/agent-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(authCookieHeader() ? { Cookie: authCookieHeader() } : {}),
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`agent-stream ${response.status}: ${(await response.text()).slice(0, 500)}`);
    }
    if (!response.body) throw new Error('empty stream body');

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let browserStart = false;
    let completion = null;
    let toolErrors = [];

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunk = consumeSseBuffer(buffer);
      buffer = chunk.remainder;
      for (const event of chunk.events) {
        allEvents.push(event);
        const type = event?.type;
        if (type === 'subagent_start' && event?.data?.agent_type === 'browser') {
          browserStart = true;
        }
        if (type === 'subagent_completion') {
          completion = event.data;
        }
        if (type === 'error') {
          toolErrors.push(eventText(event));
        }
        const blob = eventText(event);
        if (blob.includes('no tools after filtering') || blob.includes('Not in parent toolkit')) {
          toolErrors.push(blob);
        }
        if (blob.includes('Example Domain')) {
          return {
            ok: true,
            reason: 'example_domain_seen',
            browserStart,
            completion,
            chatId,
            eventCount: allEvents.length,
          };
        }
      }
    }

    return {
      ok: false,
      reason: 'stream_end_without_example_domain',
      browserStart,
      completion,
      toolErrors,
      chatId,
      types: [...new Set(allEvents.map((e) => e?.type))],
      lastEvents: allEvents.slice(-8).map((e) => ({ type: e?.type, data: e?.data })),
    };
  } finally {
    clearTimeout(timer);
  }
}

async function main() {
  await ensureLoggedIn();
  try {
    await seedProviders();
  } catch {
    /* WebUI DB providers already configured */
  }
  try {
    await putConfig('securityConfig', {
    yoloModeEnabled: true,
    yoloModeEnabledAt: Math.floor(Date.now() / 1000),
  } catch {
    /* optional */
  }

  const chatId = randomUUID();
  const messageId = randomUUID();
  const chatRes = await apiFetch('/api/v1/chats/', {
    method: 'POST',
    body: JSON.stringify({
      chat_id: chatId,
      title: `E2E Browser Delegate ${Date.now()}`,
      action_mode: 'agent',
      agent_id: 'builtin-general',
      messages: [],
    }),
  });
  if (!chatRes.ok) throw new Error(`create chat: ${await chatRes.text()}`);

  const result = await runStream(chatId, messageId);
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.ok ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
