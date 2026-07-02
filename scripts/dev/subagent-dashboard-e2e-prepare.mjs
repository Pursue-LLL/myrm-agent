#!/usr/bin/env bun
/**
 * [POS] P2c Subagent Dashboard E2E — API prepare (delegate + SSE subagent_start).
 * [OUTPUT] stdout JSON: { chatId, taskId, treeRow, uiUrl, apiBase }
 * UI phase: MCP chrome-devtools on real Chrome :3000 (not Playwright).
 */

import { randomUUID } from 'node:crypto';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? process.env.E2E_API_BASE ?? 'http://127.0.0.1:8080';
const uiBase = process.env.PLAYWRIGHT_BASE_URL ?? process.env.E2E_UI_BASE ?? 'http://127.0.0.1:3000';
const deviceId = process.env.E2E_CONFIG_DEVICE_ID ?? 'tauri-local';
const adminPassword = process.env.PLAYWRIGHT_ADMIN_PASSWORD ?? 'Playwright1234!';

const E2E_BASH_EPHEMERAL = {
  bash_worker: {
    system_prompt: 'You are a bash execution worker.',
    tools: ['bash_code_execute_tool'],
  },
};

const DELEGATE_SLEEP_QUERY =
  "请使用 delegate_task_tool 工具创建一个子智能体，必须将 agent_type 参数设置为 'bash_worker'，wait 设为 false，让它执行 bash 命令 sleep 120。注意：必须使用原生函数调用（Native Tool Calling / Function Calling）来调用工具，绝对不要在文本中输出 XML 格式的工具调用！";

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

/** @type {import('node:http').Cookie[]} */
let cookies = [];

function cookieHeader() {
  return cookies.map((c) => `${c.name}=${c.value}`).join('; ');
}

async function apiFetch(path, options = {}) {
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers ?? {}),
  };
  if (cookieHeader()) {
    headers.Cookie = cookieHeader();
  }
  const res = await fetch(`${apiBase}${path}`, {
    ...options,
    headers,
  });
  const setCookie = res.headers.getSetCookie?.() ?? [];
  for (const raw of setCookie) {
    const name = raw.split('=')[0];
    const value = raw.split('=')[1]?.split(';')[0];
    if (name && value) {
      cookies = cookies.filter((c) => c.name !== name);
      cookies.push({ name, value });
    }
  }
  return res;
}

async function ensureLoggedIn() {
  const statusRes = await apiFetch('/webui/auth/status');
  if (!statusRes.ok) {
    throw new Error(`auth status failed: ${statusRes.status}`);
  }
  const status = await statusRes.json();
  if (!status.is_setup_done) {
    throw new Error('WebUI setup not complete; log in via Chrome first');
  }
  const loginRes = await apiFetch('/webui/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username: 'admin', password: adminPassword }),
  });
  if (!loginRes.ok) {
    throw new Error(`login failed: ${loginRes.status} ${await loginRes.text()}`);
  }
}

async function putConfig(configKey, value) {
  const res = await apiFetch(`/api/v1/config/${configKey}`, {
    method: 'PUT',
    body: JSON.stringify({ value, deviceId }),
  });
  if (!res.ok) {
    throw new Error(`PUT /config/${configKey} failed: ${await res.text()}`);
  }
}

async function seedProviders() {
  const basicModel = requireEnv('BASIC_MODEL');
  const basicKey = requireEnv('BASIC_API_KEY');
  const basicUrl = process.env.BASIC_BASE_URL;
  const providerId = inferProviderId(basicModel);
  const modelId = stripProviderPrefix(basicModel);
  const resolvedUrl = basicUrl?.trim() || 'https://api.minimaxi.com/v1';
  await putConfig('providers', {
    providers: [
      {
        id: providerId,
        name: providerId === 'minimax' ? 'MiniMax' : providerId,
        routingProfile: providerId,
        isBuiltIn: providerId === 'minimax',
        isEnabled: true,
        apiUrl: resolvedUrl,
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

async function seedYoloSecurity() {
  await putConfig('securityConfig', {
    yoloModeEnabled: true,
    yoloModeEnabledAt: Math.floor(Date.now() / 1000),
  });
}

async function seedSubagentChat() {
  const chatId = randomUUID();
  const res = await apiFetch('/api/v1/chats/', {
    method: 'POST',
    body: JSON.stringify({
      chat_id: chatId,
      title: `E2E Subagent Dashboard ${Date.now()}`,
      action_mode: 'agent',
      agent_id: 'builtin-general',
      ephemeral_subagents: E2E_BASH_EPHEMERAL,
      messages: [],
    }),
  });
  if (!res.ok) {
    throw new Error(`seed chat failed: ${await res.text()}`);
  }
  return chatId;
}

function consumeSseBuffer(buffer) {
  const lines = buffer.split('\n');
  const remainder = lines.pop() ?? '';
  /** @type {Record<string, unknown>[]} */
  const events = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed.startsWith('data: ')) continue;
    try {
      events.push(JSON.parse(trimmed.slice(6)));
    } catch {
      // ignore
    }
  }
  return { events, remainder };
}

function extractRunningSubagent(events) {
  for (const event of events) {
    if (!event || event.type !== 'subagent_start') continue;
    const data = event.data;
    if (!data || typeof data !== 'object') continue;
    const taskId = data.task_id;
    if (typeof taskId !== 'string' || !taskId) continue;
    return {
      taskId,
      treeRow: {
        task_id: taskId,
        status: 'running',
        agent_type: data.agent_type ?? 'bash_worker',
        description: data.description ?? 'sleep 120',
        role: data.role ?? 'leaf',
        control_scope: data.control_scope ?? 'leaf',
      },
    };
  }
  return null;
}

function extractApprovalActionType(events) {
  for (const event of events) {
    if (!event || event.type !== 'approval_required') continue;
    const data = event.data;
    if (!data || typeof data !== 'object') return null;
    const actionType = data.action_type;
    return typeof actionType === 'string' ? actionType : null;
  }
  return null;
}

function buildAgentStreamPayload(chatId, query, messageId, resumeDecisions) {
  const basicModel = requireEnv('BASIC_MODEL');
  const providerId = inferProviderId(basicModel);
  const modelId = stripProviderPrefix(basicModel);
  /** @type {Record<string, unknown>} */
  const payload = {
    query,
    messageId,
    chatId,
    agentId: 'builtin-general',
    actionMode: 'general',
    ephemeralSubagents: E2E_BASH_EPHEMERAL,
    modelSelection: {
      providerId,
      model: modelId,
      baseUrl: process.env.BASIC_BASE_URL,
    },
  };
  if (resumeDecisions) {
    payload.resumeValue = { decisions: resumeDecisions };
  }
  return payload;
}

async function readAgentStreamUntilSubagentStart(payload, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort('agent-stream-timeout'), timeoutMs);
  /** @type {Record<string, unknown>[]} */
  const events = [];
  let capturedSeed = null;
  let needsResume = false;

  try {
    const response = await fetch(`${apiBase}/api/v1/agents/agent-stream`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(cookieHeader() ? { Cookie: cookieHeader() } : {}),
      },
      body: JSON.stringify(payload),
      signal: controller.signal,
    });
    if (!response.ok) {
      throw new Error(`agent-stream failed: ${response.status} ${(await response.text()).slice(0, 400)}`);
    }
    if (!response.body) {
      throw new Error('agent-stream returned empty body');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunk = consumeSseBuffer(buffer);
      buffer = chunk.remainder;
      events.push(...chunk.events);

      capturedSeed = extractRunningSubagent(events);
      if (capturedSeed) {
        controller.abort();
        return { seed: capturedSeed, events, needsResume: false };
      }
      if (extractApprovalActionType(events) !== null) {
        needsResume = true;
        controller.abort();
        return { seed: null, events, needsResume: true };
      }
      if (events.some((event) => event?.type === 'error')) {
        controller.abort();
        return { seed: null, events, needsResume: false };
      }
    }
    return { seed: null, events, needsResume: false };
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      if (capturedSeed) return { seed: capturedSeed, events, needsResume: false };
      if (needsResume) return { seed: null, events, needsResume: true };
      throw new Error(`agent-stream timed out after ${timeoutMs}ms without subagent_start`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function delegateSubagentViaAgentStream(chatId, timeoutMs = 180_000) {
  const deadline = Date.now() + timeoutMs;
  let query = DELEGATE_SLEEP_QUERY;
  let messageId = randomUUID();
  /** @type {Record<string, unknown>[] | undefined} */
  let resumeDecisions;

  while (Date.now() < deadline) {
    const payload = buildAgentStreamPayload(chatId, query, messageId, resumeDecisions);
    const streamBudget = Math.min(120_000, deadline - Date.now());
    const { seed, events, needsResume } = await readAgentStreamUntilSubagentStart(payload, streamBudget);
    if (seed) return seed;

    const errorEvent = events.find((event) => event?.type === 'error');
    if (errorEvent) {
      throw new Error(`agent-stream error: ${JSON.stringify(errorEvent).slice(0, 400)}`);
    }
    if (needsResume) {
      resumeDecisions = [{ type: 'approve', feedback: 'E2E auto-approve delegate/bash' }];
      query = '';
      messageId = randomUUID();
      continue;
    }
    throw new Error(
      `agent-stream finished without subagent_start; events=${events.map((e) => e?.type).join(',')}`,
    );
  }
  throw new Error(`Timed out waiting for subagent_start on chat ${chatId}`);
}

async function main() {
  requireEnv('BASIC_API_KEY');
  requireEnv('BASIC_MODEL');
  await ensureLoggedIn();
  await seedProviders();
  await seedYoloSecurity();
  const chatId = await seedSubagentChat();
  const { taskId, treeRow } = await delegateSubagentViaAgentStream(chatId);

  const result = {
    chatId,
    taskId,
    treeRow,
    uiUrl: `${uiBase}/${chatId}`,
    apiBase,
  };
  console.log(JSON.stringify(result, null, 2));
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
