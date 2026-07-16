/**
 * Idempotent provider + defaultModelConfig seed for Chrome MCP UI E2E.
 * Requires BASIC_MODEL, BASIC_API_KEY (from .env.test).
 * Local dev: /api/v1/config works without WebUI session (see config/router.py local mode).
 */

const apiBase = process.env.E2E_API_BASE ?? 'http://127.0.0.1:8080';
const deviceId = process.env.E2E_CONFIG_DEVICE_ID ?? 'chrome-e2e';

async function apiFetch(path, options = {}) {
  const res = await fetch(`${apiBase}${path}`, {
    ...options,
    signal: options.signal ?? AbortSignal.timeout(15_000),
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers ?? {}),
    },
  });
  return res;
}

function requireEnv(name) {
  const value = process.env[name];
  if (!value) {
    throw new Error(`Missing ${name}`);
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

async function hasDefaultModel() {
  const res = await apiFetch('/api/v1/config/providers');
  if (!res.ok) {
    return false;
  }
  const body = await res.json();
  const value = body?.value ?? body;
  const primary = value?.defaultModelConfig?.baseModel?.primary;
  return Boolean(primary?.providerId && primary?.model);
}

export async function seedChromeE2eProviders() {
  const forceSeed = process.env.MYRM_E2E_FORCE_MODEL_SEED === '1';
  if (!forceSeed && (await hasDefaultModel())) {
    return { seeded: false, reason: 'default_model_already_configured' };
  }
  const basicModel = requireEnv('BASIC_MODEL');
  const basicKey = requireEnv('BASIC_API_KEY');
  const basicUrl = process.env.BASIC_BASE_URL?.trim() || 'https://api.minimaxi.com/v1';
  const providerId = inferProviderId(basicModel);
  const modelId = stripProviderPrefix(basicModel);
  await putConfig('providers', {
    providers: [
      {
        id: providerId,
        name: providerId === 'minimax' ? 'MiniMax' : providerId,
        routingProfile: providerId,
        isBuiltIn: providerId === 'minimax',
        isEnabled: true,
        apiUrl: basicUrl,
        apiKeys: [{ key: basicKey, isActive: true }],
        enabledModels: [modelId],
        availableModels: [modelId],
        providerType: providerId === 'minimax' ? 'minimax' : 'openai',
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
  return { seeded: true, providerId, modelId };
}
