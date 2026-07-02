import { expect, type APIRequestContext } from '@playwright/test';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

/** Local WebUI uses TauriConfigAdapter which always syncs with this device id. */
export const E2E_CONFIG_DEVICE_ID = 'tauri-local';

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`WebUI E2E requires ${name} (load myrm-agent-server/.env.test before running Playwright)`);
  }
  return value;
}

function inferProviderId(model: string): string {
  if (model.includes('/')) {
    return model.split('/')[0] ?? 'minimax';
  }
  return 'minimax';
}

function stripProviderPrefix(model: string): string {
  if (!model.includes('/')) {
    return model;
  }
  return model.split('/').slice(1).join('/');
}

async function putConfig(
  request: APIRequestContext,
  configKey: string,
  value: Record<string, unknown>,
  deviceId: string,
): Promise<void> {
  const putRes = await request.put(`${apiBase}/api/v1/config/${configKey}`, {
    data: {
      value,
      deviceId,
    },
    timeout: 60_000,
  });
  expect(putRes.ok(), `PUT /config/${configKey} failed: ${await putRes.text()}`).toBeTruthy();
}

function buildProvidersConfigValue(
  providerId: string,
  modelId: string,
  apiKey: string,
  apiUrl: string | undefined,
): Record<string, unknown> {
  const resolvedUrl = apiUrl?.trim() || 'https://api.minimaxi.com/v1';
  return {
    providers: [
      {
        id: providerId,
        name: providerId === 'minimax' ? 'MiniMax' : providerId,
        routingProfile: providerId,
        isBuiltIn: providerId === 'minimax',
        isEnabled: true,
        apiUrl: resolvedUrl,
        apiKeys: [{ key: apiKey, isActive: true }],
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
      liteModel: {
        primary: null,
        fallback: null,
      },
      fastModeModel: null,
      routingConfig: null,
      visionFallbackModel: null,
    },
    customModelInfo: {},
  };
}

async function isProviderReady(request: APIRequestContext): Promise<boolean> {
  const readinessRes = await request.get(`${apiBase}/api/v1/config/readiness`, { timeout: 60_000 });
  if (!readinessRes.ok()) {
    return false;
  }
  const readiness = (await readinessRes.json()) as { provider?: { is_ready?: boolean } };
  return Boolean(readiness.provider?.is_ready);
}

async function seedProvidersOnce(
  request: APIRequestContext,
  deviceId: string,
): Promise<void> {
  const basicModel = requireEnv('BASIC_MODEL');
  const basicKey = requireEnv('BASIC_API_KEY');
  const basicUrl = process.env.BASIC_BASE_URL;
  const providerId = inferProviderId(basicModel);
  const modelId = stripProviderPrefix(basicModel);

  await putConfig(
    request,
    'providers',
    buildProvidersConfigValue(providerId, modelId, basicKey, basicUrl),
    deviceId,
  );

  const verifyRes = await request.get(`${apiBase}/api/v1/config/providers`);
  expect(verifyRes.ok(), `GET /config/providers failed: ${await verifyRes.text()}`).toBeTruthy();
  const verifyBody = (await verifyRes.json()) as {
    value?: { defaultModelConfig?: { baseModel?: { primary?: { model?: string } } } };
  };
  expect(verifyBody.value?.defaultModelConfig?.baseModel?.primary?.model).toBe(modelId);
}

/** Seed LLM provider + default model from process.env (BASIC_* from .env.test). */
export async function seedE2eProvidersFromEnv(
  request: APIRequestContext,
  options?: { force?: boolean; deviceId?: string },
): Promise<void> {
  const deviceId = options?.deviceId ?? E2E_CONFIG_DEVICE_ID;

  if (!options?.force && (await isProviderReady(request))) {
    return;
  }

  try {
    await seedProvidersOnce(request, deviceId);
  } catch (firstError) {
    try {
      await seedProvidersOnce(request, deviceId);
    } catch {
      throw firstError;
    }
  }
}

export function hasE2eLlmEnv(): boolean {
  return Boolean(process.env.BASIC_API_KEY && process.env.BASIC_MODEL);
}
