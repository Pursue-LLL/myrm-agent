import { describe, expect, it } from 'vitest';
import {
  BUILT_IN_PROVIDER_INFO,
  getInitialProviders,
  getLiteLLMModelName,
  hasActiveApiKey,
  hasUsableProviderAuth,
  resolveCustomProviderTypeInfo,
  resolveProviderApiKeyForRequests,
} from '../providerTypes';

describe('providerTypes defaults', () => {
  it('uses the official Xiaomi MiMo API endpoint', () => {
    expect(BUILT_IN_PROVIDER_INFO.xiaomi_mimo.defaultApiUrl).toBe('https://api.xiaomimimo.com/v1');
  });

  it('uses the OpenCode Go subscription API endpoint', () => {
    expect(BUILT_IN_PROVIDER_INFO.opencode_go.defaultApiUrl).toBe('https://opencode.ai/zen/go/v1');
    expect(getLiteLLMModelName('opencode_go', 'deepseek-v4-flash')).toBe('openai/deepseek-v4-flash');
  });

  it('seeds initial Xiaomi provider config with the same endpoint', () => {
    const xiaomiProvider = getInitialProviders().find((provider) => provider.id === 'xiaomi_mimo');

    expect(xiaomiProvider?.apiUrl).toBe('https://api.xiaomimimo.com/v1');
  });

  it('does not double-prefix Xiaomi MiMo when model already includes litellm segment', () => {
    expect(getLiteLLMModelName('xiaomi_mimo', 'mimo-v2-flash')).toBe('xiaomi_mimo/mimo-v2-flash');
    expect(getLiteLLMModelName('xiaomi_mimo', 'xiaomi_mimo/mimo-v2-flash')).toBe('xiaomi_mimo/mimo-v2-flash');
  });

  it('prefers an already-qualified LiteLLM model id over a mismatched providerId', () => {
    expect(getLiteLLMModelName('openai', 'xiaomi_mimo/mimo-v2-flash')).toBe('xiaomi_mimo/mimo-v2-flash');
  });
});

describe('resolveCustomProviderTypeInfo', () => {
  it('returns metadata for valid custom provider types', () => {
    expect(resolveCustomProviderTypeInfo('openai-like')?.litellmPrefix).toBe('openai');
    expect(resolveCustomProviderTypeInfo('anthropic-like')?.name).toBe('Anthropic-Like');
  });

  it('returns undefined for legacy bare provider ids used as providerType', () => {
    expect(resolveCustomProviderTypeInfo('openai')).toBeUndefined();
    expect(resolveCustomProviderTypeInfo('anthropic')).toBeUndefined();
    expect(resolveCustomProviderTypeInfo('ollama')).toBeUndefined();
  });
});

describe('SaaS platform provider seed auth contract', () => {
  const seededPlatformProvider = {
    id: 'platform-openrouter',
    name: 'Platform OpenRouter',
    providerType: 'openai-like' as const,
    isEnabled: true,
    apiKeys: [{ id: 'platform-managed', key: 'platform-managed', remark: '', isActive: true }],
    apiUrl: 'https://example.test/llm-relay/v1',
    enabledModels: ['anthropic/claude-sonnet-4'],
  };

  it('treats the platform-managed placeholder key as an active key', () => {
    expect(hasActiveApiKey(seededPlatformProvider)).toBe(true);
  });

  it('reports the seeded provider as usable so NoProviderBanner hides', () => {
    expect(hasUsableProviderAuth(seededPlatformProvider)).toBe(true);
  });

  it('forwards the platform-managed marker to the request key resolver', () => {
    expect(resolveProviderApiKeyForRequests(seededPlatformProvider)).toBe('platform-managed');
  });
});
