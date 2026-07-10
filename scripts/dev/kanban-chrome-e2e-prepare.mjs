#!/usr/bin/env bun
/** Kanban LLM live E2E — API prepare (auth + per-chat kanban + agent-stream). Pair with Chrome MCP on /settings/kanban for UI verification. */

import { randomUUID } from 'node:crypto';
import { ensureLoggedIn, apiFetch, apiBase } from './subagent-dashboard-e2e-auth.mjs';

const deviceId = process.env.E2E_CONFIG_DEVICE_ID ?? 'tauri-local';

function requireEnv(name) {
  const value = process.env[name];
  if (!value) throw new Error(`Missing ${name}`);
  return value;
}

function inferProviderId(model) {
  return model.includes('/') ? model.split('/')[0] : 'minimax';
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
  const basicUrl = process.env.BASIC_BASE_URL?.trim() || 'https://api.minimaxi.com/v1';
  const providerId = inferProviderId(basicModel);
  const modelId = stripProviderPrefix(basicModel);
  await putConfig('providers', {
    providers: [
      {
        id: providerId,
        name: providerId,
        routingProfile: providerId,
        isBuiltIn: false,
        isEnabled: true,
        apiUrl: basicUrl,
        apiKeys: [{ key: basicKey, isActive: true }],
        enabledModels: [modelId],
        availableModels: [modelId],
        providerType: 'openai',
      },
    ],
    defaultModelConfig: {
      baseModel: {
        primary: { providerId, model: modelId },
        fallback: null,
        temperature: 0.7,
        modelKwargs: {},
      },
      liteModel: { primary: null, fallback: null },
      fastModeModel: null,
      routingConfig: null,
      visionFallbackModel: null,
    },
    customModelInfo: {},
  });
  return { providerId, modelId };
}

async function seedYoloSecurity() {
  await putConfig('securityConfig', {
    yoloModeEnabled: true,
    yoloModeEnabledAt: Math.floor(Date.now() / 1000),
  });
}

async function createBoard() {
  const res = await apiFetch('/api/v1/kanban/boards', {
    method: 'POST',
    body: JSON.stringify({ name: `E2E Kanban ${Date.now()}`, description: 'chrome e2e' }),
  });
  if (!res.ok) throw new Error(`create board: ${await res.text()}`);
  return res.json();
}

function collectKanbanFromEvent(evt, toolNames) {
  const name = evt.tool_name ?? evt.toolName ?? evt.name ?? evt.data?.tool_name;
  if (name && String(name).startsWith('kanban_')) toolNames.add(String(name));
  if (evt.type === 'tool_start' && evt.data?.name?.startsWith?.('kanban_')) {
    toolNames.add(String(evt.data.name));
  }
}

async function streamChat(chatId, providerId, modelId) {
  const messageId = randomUUID();
  const res = await fetch(`${apiBase}/api/v1/agents/agent-stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream' },
    body: JSON.stringify({
      messageId,
      chatId,
      query:
        'CRITICAL: 你的第一步必须是调用 kanban_add_task，title 精确为 E2E-KANBAN-TEST，priority=low。' +
        '拿到 task_id 后调用 kanban_list_tasks(task_id=该ID)。最后用一句话回复 task_id 和 title。',
      modelSelection: { providerId, model: modelId },
      actionMode: 'agent',
      enableMemory: false,
      agentConfig: { enabledBuiltinTools: ['kanban'] },
    }),
  });
  if (!res.ok) throw new Error(`stream failed: ${res.status} ${await res.text()}`);

  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  const toolNames = new Set();
  let assistantText = '';
  const deadline = Date.now() + 180_000;

  while (Date.now() < deadline) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const parts = buf.split('\n');
    buf = parts.pop() ?? '';
    for (const line of parts) {
      if (!line.startsWith('data: ')) continue;
      const payload = line.slice(6).trim();
      if (!payload || payload === '[DONE]') continue;
      try {
        const evt = JSON.parse(payload);
        collectKanbanFromEvent(evt, toolNames);
        if (evt.type === 'message' && typeof evt.data === 'string') assistantText += evt.data;
        const chunk = evt.content ?? evt.text ?? evt.delta;
        if (typeof chunk === 'string') assistantText += chunk;
      } catch {
        /* ignore partial JSON */
      }
    }
  }

  return { kanbanTools: [...toolNames], assistantTail: assistantText.slice(-800) };
}

function normalizeTasks(body) {
  if (Array.isArray(body)) return body;
  if (Array.isArray(body?.items)) return body.items;
  if (Array.isArray(body?.tasks)) return body.tasks;
  if (Array.isArray(body?.data?.items)) return body.data.items;
  return [];
}

await ensureLoggedIn();
const { providerId, modelId } = await seedProviders();
await seedYoloSecurity();
const board = await createBoard();
const chatId = randomUUID();
const chatRes = await apiFetch('/api/v1/chats/', {
  method: 'POST',
  body: JSON.stringify({ chat_id: chatId, title: `Kanban E2E ${Date.now()}`, action_mode: 'agent' }),
});
if (!chatRes.ok) throw new Error(`chat create: ${await chatRes.text()}`);

const stream = await streamChat(chatId, providerId, modelId);
let e2eTask = null;
const taskIdMatch = stream.assistantTail.match(/[a-f0-9]{12}/i);
if (taskIdMatch) {
  const taskRes = await apiFetch(`/api/v1/kanban/tasks/${taskIdMatch[0]}`);
  if (taskRes.ok) {
    const body = await taskRes.json();
    e2eTask = { id: body.task_id ?? body.id, title: body.title, task_id: body.task_id };
  }
}
if (!e2eTask && stream.kanbanTools.length > 0) {
  const boardsRes = await apiFetch('/api/v1/kanban/boards');
  if (boardsRes.ok) {
    const boardsBody = await boardsRes.json();
    const boards = Array.isArray(boardsBody) ? boardsBody : boardsBody.items ?? boardsBody.data?.items ?? [];
    for (const board of boards) {
      const bid = board.board_id ?? board.id;
      if (!bid) continue;
      const tasksRes = await apiFetch(`/api/v1/kanban/boards/${bid}/tasks`);
      if (!tasksRes.ok) continue;
      const tasksBody = await tasksRes.json();
      const tasks = normalizeTasks(tasksBody);
      const hit = tasks.find((t) => String(t.title ?? '').includes('E2E-KANBAN-TEST'));
      if (hit) {
        e2eTask = { id: hit.id ?? hit.task_id, title: hit.title, task_id: hit.task_id ?? hit.id };
        break;
      }
    }
  }
}

console.log(
  JSON.stringify(
    {
      ok: Boolean(e2eTask),
      model: `${providerId}/${modelId}`,
      boardId: board.board_id ?? board.id,
      chatId,
      uiUrl: `http://127.0.0.1:3000/${chatId}`,
      kanbanUrl: 'http://127.0.0.1:3000/settings/kanban',
      kanbanToolsInvoked: stream.kanbanTools,
      e2eTask: e2eTask ? { id: e2eTask.id ?? e2eTask.task_id, title: e2eTask.title } : null,
      assistantTail: stream.assistantTail,
    },
    null,
    2,
  ),
);

if (!e2eTask) process.exit(1);
