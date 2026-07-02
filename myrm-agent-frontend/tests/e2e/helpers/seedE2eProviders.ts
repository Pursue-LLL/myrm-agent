import { expect, type APIRequestContext } from '@playwright/test';

const apiBase = process.env.PLAYWRIGHT_API_BASE ?? 'http://127.0.0.1:8080';

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(`WebUI E2E requires ${name} (load myrm-agent-server/.env.test before running Playwright)`);
  }
  return value;
}

function inferProviderId(model: string): string {
  if (model.includes('/')) {
    return model.split('/')[0] ?? 'default';
  }
  return 'default';
}

function stripProviderPrefix(model: string): string {
  if (!model.includes('/')) {
    return model;
  }
  return model.split('/').slice(1).join('/');
}

function resolveProviderType(providerId: string): string {
  const normalized = providerId.replace(/-/g, '_');
  if (normalized === 'minimax') {
    return 'minimax';
  }
  if (normalized === 'openai_like' || normalized === 'openai_compatible') {
    return 'openai';
  }
  return normalized;
}

async function putConfig(
  request: APIRequestContext,
  configKey: string,
  value: Record<string, unknown>,
): Promise<void> {
  const putRes = await request.put(`${apiBase}/api/v1/config/${configKey}`, {
    data: {
      value,
      deviceId: 'playwright-e2e',
    },
    timeout: 60_000,
  });
  expect(putRes.ok(), `PUT /config/${configKey} failed: ${await putRes.text()}`).toBeTruthy();
}

/** Seed LLM provider + default model from process.env (BASIC_* from .env.test). */
export async function seedE2eProvidersFromEnv(request: APIRequestContext): Promise<void> {
  const readinessRes = await request.get(`${apiBase}/api/v1/config/readiness`, { timeout: 60_000 });
  if (readinessRes.ok()) {
    const readiness = (await readinessRes.json()) as { provider?: { is_ready?: boolean } };
    if (readiness.provider?.is_ready) {
      return;
    }
  }

  const basicModel = requireEnv('BASIC_MODEL');
  const basicKey = requireEnv('BASIC_API_KEY');
  const basicUrl = process.env.BASIC_BASE_URL;
  const providerId = inferProviderId(basicModel);
  const modelId = stripProviderPrefix(basicModel);

  await putConfig(request, 'providers', {
    providers: [
      {
        id: providerId,
        providerType: resolveProviderType(providerId),
        isEnabled: true,
        apiUrl: basicUrl,
        apiKeys: [{ key: basicKey, isActive: true }],
        enabledModels: [modelId],
      },
    ],
    defaultModelConfig: {
      baseModel: {
        primary: {
          providerId,
          model: modelId,
        },
      },
    },
  });
}

export function hasE2eLlmEnv(): boolean {
  return Boolean(process.env.BASIC_API_KEY && process.env.BASIC_MODEL);
}
