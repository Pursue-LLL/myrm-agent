#!/usr/bin/env bun
/**
 * [POS] MoA overlay E2E — API prepare (agent with overlay + SSE moa_ref_done).
 * [OUTPUT] stdout: E2E_PREPARE_JSON={ agentId, chatId, uiUrl, moaOverlayActive, moaRefDoneCount, apiBase }
 * UI phase: MCP chrome-devtools on real Chrome (not Playwright).
 *
 * Env: E2E_API_BASE (default http://127.0.0.1:8080), E2E_UI_BASE, E2E_MOA_PRESET_ID (default),
 * E2E_MOA_STREAM_TIMEOUT_MS, BASIC_* from myrm-agent-server/.env.test
 */

import { randomUUID } from 'node:crypto';
import { apiBase, apiFetch, authCookieHeader, ensureLoggedIn } from './subagent-dashboard-e2e-auth.mjs';

const uiBase = process.env.E2E_UI_BASE ?? 'http://127.0.0.1:3000';
const deviceId = process.env.E2E_CONFIG_DEVICE_ID ?? 'tauri-local';
const moaPresetId = process.env.E2E_MOA_PRESET_ID ?? 'default';
const streamTimeoutMs = Number(process.env.E2E_MOA_STREAM_TIMEOUT_MS ?? 120_000);

const MOA_QUERY =
  '用一句话解释：什么是 Mixture-of-Agents（MoA）顾问叠加？不要调用任何工具，直接文字回答。';

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
  return { providerId, modelId };
}

async function createMoaAgent(providerId, modelId) {
  const suffix = Date.now();
  const res = await apiFetch('/api/v1/user-agents', {
    method: 'POST',
    body: JSON.stringify({
      name: `E2E MoA Overlay ${suffix}`,
      description: 'Temporary agent for MoA overlay E2E',
      model_selection: { providerId, model: modelId },
      engine_params: {
        moa_overlay: {
          enabled: true,
          fanout: 'user_turn',
          every_n: 2,
          min_successful: 1,
          reference_temperature: 0.6,
          reference_max_tokens: 300,
          reference_reasoning_effort: 'low',
          privacy_filter: 'off',
          reference_model_selections: [
            { providerId, model: modelId },
            { providerId, model: modelId },
          ],
        },
      },
    }),
  });
  if (!res.ok) {
    throw new Error(`create agent failed: ${await res.text()}`);
  }
  const json = await res.json();
  const agentId = json?.data?.id;
  if (typeof agentId !== 'string' || !agentId) {
    throw new Error(`create agent missing id: ${JSON.stringify(json).slice(0, 400)}`);
  }
  return agentId;
}

async function deleteAgent(agentId) {
  const res = await apiFetch(`/api/v1/user-agents/${agentId}`, { method: 'DELETE' });
  if (!res.ok && res.status !== 404) {
    console.warn(`delete agent failed: ${(await res.text()).slice(0, 400)}`);
  }
}

async function createChat(agentId) {
  const chatId = randomUUID();
  const res = await apiFetch('/api/v1/chats/', {
    method: 'POST',
    body: JSON.stringify({
      chat_id: chatId,
      title: `E2E MoA Overlay ${Date.now()}`,
      action_mode: 'agent',
      agent_id: agentId,
      messages: [],
    }),
  });
  if (!res.ok) {
    throw new Error(`seed chat failed: ${await res.text()}`);
  }
  return chatId;
}

async function activateChatMoaPreset(chatId, presetId) {
  const res = await apiFetch(`/api/v1/chats/${chatId}/active-moa-preset`, {
    method: 'PATCH',
    body: JSON.stringify({ active_moa_preset_id: presetId }),
  });
  if (!res.ok) {
    throw new Error(`PATCH active-moa-preset failed: ${await res.text()}`);
  }
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
      // ignore malformed chunks
    }
  }
  return { events, remainder };
}

function countMoaEvents(events) {
  let moaOverlayActive = false;
  let moaRefDoneCount = 0;
  for (const event of events) {
    if (event?.type !== 'status') continue;
    const stepKey = event.step_key;
    if (stepKey === 'moa_overlay_active') {
      moaOverlayActive = true;
    }
    if (stepKey === 'moa_ref_done') {
      moaRefDoneCount += 1;
    }
  }
  return { moaOverlayActive, moaRefDoneCount };
}

async function runAgentStreamUntilMoa(chatId, agentId, providerId, modelId, presetId) {
  const messageId = randomUUID();
  const payload = {
    query: MOA_QUERY,
    messageId,
    chatId,
    agentId,
    actionMode: 'agent',
    active_moa_preset_id: presetId,
    modelSelection: {
      providerId,
      model: modelId,
      baseUrl: process.env.BASIC_BASE_URL,
    },
  };

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort('moa-stream-timeout'), streamTimeoutMs);
  /** @type {Record<string, unknown>[]} */
  const events = [];

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
      throw new Error(`agent-stream failed: ${response.status} ${(await response.text()).slice(0, 400)}`);
    }
    if (!response.body) {
      throw new Error('agent-stream returned empty body');
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    let counts = { moaOverlayActive: false, moaRefDoneCount: 0 };

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const chunk = consumeSseBuffer(buffer);
      buffer = chunk.remainder;
      events.push(...chunk.events);
      counts = countMoaEvents(events);
      if (counts.moaOverlayActive && counts.moaRefDoneCount >= 1) {
        controller.abort();
        break;
      }
      const errorEvent = events.find((event) => event?.type === 'error');
      if (errorEvent) {
        throw new Error(`agent-stream error: ${JSON.stringify(errorEvent).slice(0, 400)}`);
      }
    }

    if (!counts.moaOverlayActive || counts.moaRefDoneCount < 1) {
      throw new Error(
        `MoA overlay SSE not observed (active=${counts.moaOverlayActive}, refDone=${counts.moaRefDoneCount}); ` +
          `steps=${events.filter((e) => e?.type === 'status').map((e) => e.step_key).join(',')}`,
      );
    }
    return counts;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      const counts = countMoaEvents(events);
      if (counts.moaRefDoneCount >= 1) {
        return counts;
      }
      const steps = events
        .filter((e) => e?.type === 'status')
        .map((e) => e.step_key)
        .join(',');
      throw new Error(
        `moa-stream-timeout (active=${counts.moaOverlayActive}, refDone=${counts.moaRefDoneCount}; steps=${steps || 'none'})`,
      );
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

async function main() {
  requireEnv('BASIC_API_KEY');
  requireEnv('BASIC_MODEL');
  await ensureLoggedIn();

  const snapshots = { providers: await readConfig('providers') };
  let restored = false;
  let agentId = null;

  try {
    const { providerId, modelId } = await seedProviders();
    agentId = await createMoaAgent(providerId, modelId);
    const chatId = await createChat(agentId);
    await activateChatMoaPreset(chatId, moaPresetId);
    const { moaOverlayActive, moaRefDoneCount } = await runAgentStreamUntilMoa(
      chatId,
      agentId,
      providerId,
      modelId,
      moaPresetId,
    );

    const result = {
      agentId,
      chatId,
      uiUrl: `${uiBase}/${chatId}`,
      apiBase,
      activeMoaPresetId: moaPresetId,
      moaOverlayActive,
      moaRefDoneCount,
    };
    console.log(`E2E_PREPARE_JSON=${JSON.stringify(result)}`);

    await restoreConfig('providers', snapshots.providers);
    restored = true;
  } finally {
    if (agentId) {
      await deleteAgent(agentId);
    }
    if (!restored) {
      await restoreConfig('providers', snapshots.providers);
    }
  }
}

main().catch((error) => {
  console.error(error instanceof Error ? error.message : String(error));
  process.exit(1);
});
