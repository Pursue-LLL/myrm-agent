/**
 * Idempotent provider + defaultModelConfig seed for Chrome MCP UI E2E.
 * Requires BASIC_MODEL, BASIC_API_KEY (from .env.test); optional LITE_MODEL seeds liteModel.primary.
 * Local dev: /api/v1/config works without WebUI session (see config/router.py local mode).
 */

const apiBase = process.env.E2E_API_BASE ?? 'http://127.0.0.1:8080';
const deviceId = process.env.E2E_CONFIG_DEVICE_ID ?? 'chrome-e2e';

function resolveSeedTimeoutMs() {
  const raw = process.env.MYRM_E2E_MODEL_SEED_TIMEOUT_MS?.trim();
  if (raw && /^\d+$/.test(raw)) {
    return Number(raw);
  }
  const leasesRaw = process.env.MYRM_E2E_PARALLEL_ACTIVE_LEASES?.trim();
  const leases =
    leasesRaw && /^\d+$/.test(leasesRaw) ? Number(leasesRaw) : 0;
  return Math.min(60_000, 15_000 + Math.min(leases, 6) * 5_000);
}

async function apiFetch(path, options = {}) {
  const res = await fetch(`${apiBase}${path}`, {
    ...options,
    signal: options.signal ?? AbortSignal.timeout(resolveSeedTimeoutMs()),
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

function providerType(providerId) {
  const normalized = providerId.replace(/-/g, '_');
  if (normalized === 'minimax') {
    return 'minimax';
  }
  if (normalized === 'openai' || normalized === 'openai_like' || normalized === 'openai_compatible') {
    return 'openai';
  }
  return normalized;
}

function providerDisplayName(providerId, apiUrl) {
  if (apiUrl.includes('opencode.ai')) {
    return 'OpenCode Go';
  }
  if (providerId === 'minimax') {
    return 'MiniMax';
  }
  return providerId;
}

function normalizeApiUrl(url) {
  return (url ?? '').trim().replace(/\/$/, '');
}

function activeApiKey(provider) {
  const keys = provider?.apiKeys;
  if (!Array.isArray(keys) || keys.length === 0) {
    return '';
  }
  const active = keys.find((item) => item?.isActive);
  return (active?.key ?? keys[0]?.key ?? '').trim();
}

function providerEndpointDrift(existing, { apiUrl, apiKey }) {
  if (!existing) {
    return false;
  }
  return (
    normalizeApiUrl(existing.apiUrl) !== normalizeApiUrl(apiUrl) ||
    activeApiKey(existing) !== (apiKey ?? '').trim()
  );
}

function upsertProviderEntry(byId, entry) {
  const existing = byId.get(entry.id);
  if (!existing) {
    byId.set(entry.id, entry);
    return true;
  }
  const mergedModels = [
    ...new Set([...(existing.enabledModels ?? []), ...entry.enabledModels]),
  ];
  const endpointDrift = providerEndpointDrift(existing, entry);
  const modelsChanged =
    mergedModels.length !== (existing.enabledModels ?? []).length ||
    mergedModels.some((model) => !(existing.enabledModels ?? []).includes(model));
  byId.set(entry.id, {
    ...existing,
    name: entry.name,
    apiUrl: entry.apiUrl,
    apiKeys: entry.apiKeys,
    providerType: entry.providerType,
    routingProfile: entry.routingProfile ?? existing.routingProfile ?? entry.id,
    isEnabled: true,
    enabledModels: mergedModels,
    availableModels: mergedModels,
  });
  return endpointDrift || modelsChanged;
}

function buildProviderEntry({ providerId, modelId, apiUrl, apiKey }) {
  return {
    id: providerId,
    name: providerDisplayName(providerId, apiUrl),
    routingProfile: providerId,
    isBuiltIn: providerId === 'minimax',
    isEnabled: true,
    apiUrl,
    apiKeys: [{ key: apiKey, isActive: true }],
    enabledModels: [modelId],
    availableModels: [modelId],
    providerType: providerType(providerId),
  };
}

function mergeProviders(basicEntry, liteEntry) {
  if (!liteEntry || basicEntry.id === liteEntry.id) {
    const mergedModels = [...new Set([...basicEntry.enabledModels, ...(liteEntry?.enabledModels ?? [])])];
    return [{ ...basicEntry, enabledModels: mergedModels, availableModels: mergedModels }];
  }
  return [basicEntry, liteEntry];
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

async function readProvidersConfig() {
  const res = await apiFetch('/api/v1/config/providers');
  if (!res.ok) {
    return null;
  }
  const body = await res.json();
  return body?.value ?? body;
}

async function ensureProvidersFromEnv(existingConfig) {
  const config = existingConfig ?? (await readProvidersConfig());
  if (!config) {
    return { patched: false, reason: 'providers_unreadable' };
  }

  // An existing default model is not proof that the complete E2E provider
  // catalog is present. PRIVATE runtimes can reuse a database seeded by a
  // previous test (for example, with only the lite MiniMax provider). Always
  // reconcile both env-declared providers before the UI policy E2E runs.
  const basicModelRaw = process.env.BASIC_MODEL?.trim();
  const basicKey = process.env.BASIC_API_KEY?.trim();
  const basicUrl = process.env.BASIC_BASE_URL?.trim() || 'https://api.minimaxi.com/v1';
  const basicEntry =
    basicModelRaw && basicKey
      ? buildProviderEntry({
          providerId: inferProviderId(basicModelRaw),
          modelId: stripProviderPrefix(basicModelRaw),
          apiUrl: basicUrl,
          apiKey: basicKey,
        })
      : null;

  const liteModelRaw = process.env.LITE_MODEL?.trim();
  if (!liteModelRaw && !basicEntry) {
    return { patched: false, reason: 'no_provider_env' };
  }

  const litePrimary = config?.defaultModelConfig?.liteModel?.primary;
  const expectedProviderId = liteModelRaw ? inferProviderId(liteModelRaw) : null;
  const expectedModelId = liteModelRaw ? stripProviderPrefix(liteModelRaw) : null;
  const liteKey = process.env.LITE_API_KEY?.trim() || basicKey;
  const liteUrl = process.env.LITE_BASE_URL?.trim() || basicUrl;
  const liteProviderId = liteModelRaw ? inferProviderId(liteModelRaw) : null;
  const liteModelId = liteModelRaw ? stripProviderPrefix(liteModelRaw) : null;
  if (liteModelRaw && !liteKey) {
    throw new Error('Missing LITE_API_KEY or BASIC_API_KEY for lite model seed');
  }
  const liteEntry =
    liteModelRaw && liteProviderId && liteModelId
      ? buildProviderEntry({
          providerId: liteProviderId,
          modelId: liteModelId,
          apiUrl: liteUrl,
          apiKey: liteKey,
        })
      : null;

  const existingProviders = Array.isArray(config.providers) ? config.providers : [];
  const byId = new Map(existingProviders.map((provider) => [provider.id, provider]));
  const existingBasic = basicEntry ? byId.get(basicEntry.id) : null;
  const existingLite = byId.get(liteProviderId);
  const basicChanged = basicEntry ? upsertProviderEntry(byId, basicEntry) : false;
  const liteChanged = liteEntry ? upsertProviderEntry(byId, liteEntry) : false;
  const providerChanged = basicChanged || liteChanged;
  const primaryMatches =
    !liteEntry ||
    (litePrimary?.providerId === expectedProviderId && litePrimary?.model === expectedModelId);
  const endpointDrift =
    (basicEntry && providerEndpointDrift(existingBasic, basicEntry)) ||
    (liteEntry && providerEndpointDrift(existingLite, liteEntry));

  if (primaryMatches && !providerChanged && !endpointDrift) {
    return {
      patched: false,
      reason: 'providers_already_configured',
      litePrimary,
      basicProviderId: basicEntry?.id ?? null,
    };
  }

  const defaultModelConfig = {
    ...(config.defaultModelConfig ?? {}),
    ...(liteEntry
      ? {
          liteModel: {
            ...(config.defaultModelConfig?.liteModel ?? {}),
            primary: { providerId: liteProviderId, model: liteModelId },
            fallback: config.defaultModelConfig?.liteModel?.fallback ?? null,
          },
          fastModeModel: {
            ...(config.defaultModelConfig?.fastModeModel ?? {}),
            primary: { providerId: liteProviderId, model: liteModelId },
            fallback: config.defaultModelConfig?.fastModeModel?.fallback ?? null,
            temperature:
              config.defaultModelConfig?.fastModeModel?.temperature ??
              config.defaultModelConfig?.baseModel?.temperature ??
              0.7,
            modelKwargs:
              config.defaultModelConfig?.fastModeModel?.modelKwargs ??
              config.defaultModelConfig?.baseModel?.modelKwargs ??
              {},
          },
        }
      : {}),
  };

  await putConfig('providers', {
    ...config,
    providers: [...byId.values()],
    defaultModelConfig,
    customModelInfo: config.customModelInfo ?? {},
  });
  return {
    patched: true,
    basicProviderId: basicEntry?.id ?? null,
    basicModelId: basicEntry?.enabledModels?.[0] ?? null,
    liteProviderId: liteProviderId ?? null,
    liteModelId: liteModelId ?? null,
    endpointDrift,
  };
}

export async function seedChromeE2eProviders() {
  const forceSeed = process.env.MYRM_E2E_FORCE_MODEL_SEED === '1';
  if (!forceSeed && (await hasDefaultModel())) {
    const providerPatch = await ensureProvidersFromEnv();
    return { seeded: false, reason: 'default_model_already_configured', ...providerPatch };
  }
  const basicModel = requireEnv('BASIC_MODEL');
  const basicKey = requireEnv('BASIC_API_KEY');
  const basicUrl = process.env.BASIC_BASE_URL?.trim() || 'https://api.minimaxi.com/v1';
  const providerId = inferProviderId(basicModel);
  const modelId = stripProviderPrefix(basicModel);
  const basicEntry = buildProviderEntry({
    providerId,
    modelId,
    apiUrl: basicUrl,
    apiKey: basicKey,
  });

  const liteModelRaw = process.env.LITE_MODEL?.trim();
  let litePrimary = null;
  let liteEntry = null;
  if (liteModelRaw) {
    const liteKey = process.env.LITE_API_KEY?.trim() || basicKey;
    const liteUrl = process.env.LITE_BASE_URL?.trim() || basicUrl;
    const liteProviderId = inferProviderId(liteModelRaw);
    const liteModelId = stripProviderPrefix(liteModelRaw);
    litePrimary = { providerId: liteProviderId, model: liteModelId };
    liteEntry = buildProviderEntry({
      providerId: liteProviderId,
      modelId: liteModelId,
      apiUrl: liteUrl,
      apiKey: liteKey,
    });
  }

  const basePrimary = { providerId, model: modelId };
  await putConfig('providers', {
    providers: mergeProviders(basicEntry, liteEntry),
    defaultModelConfig: {
      baseModel: {
        primary: basePrimary,
        fallback: null,
        temperature: 0.7,
        modelKwargs: {},
      },
      liteModel: {
        primary: litePrimary,
        fallback: null,
      },
      fastModeModel: null,
      routingConfig: null,
      visionFallbackModel: null,
    },
    customModelInfo: {},
  });
  return {
    seeded: true,
    providerId,
    modelId,
    liteProviderId: litePrimary?.providerId ?? null,
    liteModelId: litePrimary?.model ?? null,
  };
}
