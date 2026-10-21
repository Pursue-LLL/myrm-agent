#!/usr/bin/env bun
/**
 * [POS] P2c Subagent Dashboard E2E — API prepare (delegate + SSE subagent_start).
 * [OUTPUT] stdout JSON: { chatId, taskId, treeRow, uiUrl, apiBase }
 * UI phase: MCP chrome-devtools on real Chrome :3000 (not Playwright).
 */

import { randomUUID } from 'node:crypto';
import { spawnSync } from 'node:child_process';
import { appendFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { apiBase, apiFetch, authCookieHeader, ensureLoggedIn } from './subagent-dashboard-e2e-auth.mjs';

const DIAG_LOG = '/tmp/subagent-prepare-diag.log';

function diag(message) {
  try {
    appendFileSync(DIAG_LOG, `${new Date().toISOString()} ${message}\n`);
  } catch {
    /* diagnostics are best-effort */
  }
}

const uiBase = process.env.E2E_UI_BASE ?? 'http://127.0.0.1:3000';
const deviceId = process.env.E2E_CONFIG_DEVICE_ID ?? 'tauri-local';
const streamHoldMs = Number(process.env.E2E_HOLD_MS ?? 120_000);

// --seed-config-only: seed providers + YOLO securityConfig, then hold the process
// until SIGTERM (which restores the snapshots). Used by frontend_full_flow E2E to
// make the WebUI send flow delegate without HITL approval on a PRIVATE backend.
const seedConfigOnly = process.argv.includes('--seed-config-only');
const SEED_CONFIG_HOLD_MAX_MS = 900_000;

let _restoreSnapshot = null;
process.on('SIGTERM', () => void handleShutdownSignal());
process.on('SIGINT', () => void handleShutdownSignal());

async function handleShutdownSignal() {
  try {
    if (_restoreSnapshot) {
      await _restoreSnapshot();
    }
  } catch (error) {
    diag(`restore_on_signal_failed:${error instanceof Error ? error.message : String(error)}`);
  }
  process.exit(0);
}

const E2E_BASH_EPHEMERAL = {
  bash_worker: {
    system_prompt: 'You are a bash execution worker.',
    tools: ['bash_code_execute_tool'],
  },
};

const DELEGATE_SLEEP_QUERY =
  "请使用 delegate_task_tool 工具创建一个子智能体，必须将 agent_type 参数设置为 'bash_worker'，wait 设为 false。" +
  "子智能体的任务：调用 bash_code_execute_tool 执行命令 `sleep 300`，关键要求：run_in_background 必须为 false（前台运行），" +
  "timeout 参数必须显式设为 600，绝对禁止使用后台方式或 & 符号，必须等待命令完成后才能汇报结果并结束。" +
  "注意：必须使用原生函数调用（Native Tool Calling / Function Calling）来调用工具，绝对不要在文本中输出 XML 格式的工具调用！";

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing ${name} (source myrm-agent-server/.env.test)`);
  }
  return value;
}

function registerWaveLedger(chatId) {
  const leaseId = process.env.WAVE_LEDGER_LEASE_ID?.trim();
  if (!leaseId || !chatId) {
    return;
  }
  const scriptDir = path.dirname(fileURLToPath(import.meta.url));
  const waveSh = path.join(scriptDir, 'wave.sh');
  const agentId = process.env.MYRM_WAVE_AGENT_ID?.trim() || `subagent-e2e:${process.pid}`;
  const namespace = process.env.WAVE_LEDGER_NAMESPACE?.trim() ?? '';
  const args = [
    waveSh,
    '--agent',
    agentId,
    'ledger',
    'register',
    leaseId,
    'chat',
    chatId,
  ];
  if (namespace) {
    args.push('--namespace', namespace);
  }
  const result = spawnSync('bash', args, { encoding: 'utf-8' });
  if (result.status !== 0) {
    const detail = (result.stderr || result.stdout || '').trim();
    throw new Error(`wave ledger register failed: ${detail || `exit ${result.status}`}`);
  }
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

async function putConfig(configKey, value) {
  const res = await apiFetch(`/api/v1/config/${configKey}`, {
    method: 'PUT',
    body: JSON.stringify({ value, deviceId }),
  });
  if (!res.ok) {
    throw new Error(`PUT /config/${configKey} failed: ${await res.text()}`);
  }
}

async function readConfig(configKey) {
  const res = await apiFetch(`/api/v1/config/${configKey}`);
  if (res.status === 404) return { exists: false, value: null };
  if (!res.ok) throw new Error(`GET /config/${configKey} failed: ${await res.text()}`);
  const body = await res.json();
  return { exists: true, value: body.value };
}

async function restoreConfig(configKey, snapshot) {
  if (snapshot.exists) {
    await putConfig(configKey, snapshot.value);
    return;
  }
  const res = await apiFetch(`/api/v1/config/${configKey}`, { method: 'DELETE' });
  if (!res.ok && res.status !== 404) {
    throw new Error(`DELETE /config/${configKey} failed: ${await res.text()}`);
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
    diag(`post:${apiBase}/api/v1/agents/agent-stream body_keys=${Object.keys(payload).join(',')}`);
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
      diag(`http_status:${response.status}`);
      throw new Error(`agent-stream failed: ${response.status} ${(await response.text()).slice(0, 400)}`);
    }
    diag(`http_ok:${response.status} has_body=${Boolean(response.body)}`);
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
      diag(`sse:${events.map((e) => e?.type).join(',')}`);

      capturedSeed = extractRunningSubagent(events);
      if (capturedSeed) {
        const keepStreamAlive = async () => {
          const until = Date.now() + streamHoldMs;
          try {
            while (Date.now() < until) {
              const next = await reader.read();
              if (next.done) break;
              if (next.value) {
                buffer += decoder.decode(next.value, { stream: true });
                const chunk = consumeSseBuffer(buffer);
                buffer = chunk.remainder;
              }
            }
          } catch {
            /* stream closed */
          }
        };
        return { seed: capturedSeed, events, needsResume: false, keepStreamAlive };
      }
      if (extractApprovalActionType(events) !== null) {
        needsResume = true;
        controller.abort();
        return { seed: null, events, needsResume: true, keepStreamAlive: null };
      }
      if (events.some((event) => event?.type === 'error')) {
        controller.abort();
        return { seed: null, events, needsResume: false, keepStreamAlive: null };
      }
    }
    return { seed: null, events, needsResume: false, keepStreamAlive: null };
  } catch (error) {
    diag(`error:name=${error?.name} message=${error instanceof Error ? error.message : String(error)}`);
    if (error instanceof Error && error.name === 'AbortError') {
      if (capturedSeed) return { seed: capturedSeed, events, needsResume: false, keepStreamAlive: null };
      if (needsResume) return { seed: null, events, needsResume: true, keepStreamAlive: null };
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
    diag(`attempt:${messageId} budget=${streamBudget}ms query_len=${query.length} resume=${resumeDecisions?.length ?? 0}`);
    const { seed, events, needsResume, keepStreamAlive } = await readAgentStreamUntilSubagentStart(payload, streamBudget);
    diag(`attempt_done:${messageId} seed=${Boolean(seed)} needsResume=${needsResume} events=${events.map((e) => e?.type).join(',')}`);
    if (seed) return { ...seed, keepStreamAlive };

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

async function assertListSubagents(chatId, taskId) {
  const res = await apiFetch(`/api/v1/chats/${chatId}/subagents`);
  if (!res.ok) {
    throw new Error(`GET /subagents failed: ${res.status} ${(await res.text()).slice(0, 400)}`);
  }
  const json = await res.json();
  const rows = Array.isArray(json.data) ? json.data : [];
  const row = rows.find((entry) => entry?.task_id === taskId);
  if (!row) {
    throw new Error(`GET /subagents missing task ${taskId}; rows=${JSON.stringify(rows).slice(0, 400)}`);
  }
  if (row.status !== 'running') {
    throw new Error(`GET /subagents expected running status for ${taskId}, got ${String(row.status)}`);
  }
}

async function assertListSubagentsStillRunning(chatId, taskId, delayMs = 2000) {
  await new Promise((resolve) => setTimeout(resolve, delayMs));
  await assertListSubagents(chatId, taskId);
}

async function main() {
  requireEnv('BASIC_API_KEY');
  requireEnv('BASIC_MODEL');
  await ensureLoggedIn();
  const snapshots = {
    providers: await readConfig('providers'),
    securityConfig: await readConfig('securityConfig'),
  };
  const restoreAll = async () => {
    await restoreConfig('providers', snapshots.providers);
    await restoreConfig('securityConfig', snapshots.securityConfig);
  };
  if (seedConfigOnly) {
    await seedProviders();
    await seedYoloSecurity();
    _restoreSnapshot = restoreAll;
    console.log(`E2E_PREPARE_JSON=${JSON.stringify({ seeded: true, uiBase, apiBase })}`);
    const deadline = Date.now() + SEED_CONFIG_HOLD_MAX_MS;
    while (Date.now() < deadline) {
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    await restoreAll();
    return;
  }
  let restored = false;
  try {
    await seedProviders();
    await seedYoloSecurity();
    const chatArg = process.argv.find((arg) => arg.startsWith("--chat="));
    const chatId = chatArg ? chatArg.split("=")[1] ?? "" : "";
    const resolvedChatId = chatId || (await seedSubagentChat());
    registerWaveLedger(resolvedChatId);
    const { taskId, treeRow, keepStreamAlive } = await delegateSubagentViaAgentStream(
      resolvedChatId,
    );
    await assertListSubagents(resolvedChatId, taskId);
    await assertListSubagentsStillRunning(resolvedChatId, taskId);

    const result = {
      chatId: resolvedChatId,
      taskId,
      treeRow,
      uiUrl: `${uiBase}/${resolvedChatId}`,
      apiBase,
    };
    console.log(`E2E_PREPARE_JSON=${JSON.stringify(result)}`);

    if (keepStreamAlive && streamHoldMs > 0) {
      await keepStreamAlive();
      // Parent stream may finish before streamHoldMs; keep prepare alive so UI/MCP can reach list/cancel.
      await new Promise((resolve) => setTimeout(resolve, streamHoldMs));
    }
    await restoreAll();
    restored = true;
  } finally {
    if (!restored) {
      await restoreAll();
    }
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
