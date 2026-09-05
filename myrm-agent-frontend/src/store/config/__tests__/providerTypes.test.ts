import { describe, expect, it } from 'vitest';
import {
  BUILT_IN_PROVIDER_INFO,
  getInitialProviders,
  getLiteLLMModelName,
  hasActiveApiKey,
  hasUsableProviderAuth,
  isLocalOrTrustedSplitStackApiUrl,
  isLoopbackApiUrl,
  isTrustedSplitStackHostname,
  LOCAL_NO_AUTH_API_KEY_MARKER,
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

describe('isTrustedSplitStackHostname and URL helpers', () => {
  it('correctly classifies loopback, RFC1918, Tailscale, and mDNS as trusted split-stack hostnames', () => {
    expect(isTrustedSplitStackHostname('localhost')).toBe(true);
    expect(isTrustedSplitStackHostname('127.0.0.1')).toBe(true);
    expect(isTrustedSplitStackHostname('10.0.0.1')).toBe(true);
    expect(isTrustedSplitStackHostname('172.16.0.1')).toBe(true);
    expect(isTrustedSplitStackHostname('172.31.255.254')).toBe(true);
    expect(isTrustedSplitStackHostname('192.168.1.100')).toBe(true);
    expect(isTrustedSplitStackHostname('100.80.20.10')).toBe(true);
    expect(isTrustedSplitStackHostname('mac-mini.local')).toBe(true);
  });

  it('rejects cloud link-local metadata, public IPs, and external domains', () => {
    expect(isTrustedSplitStackHostname('169.254.169.254')).toBe(false);
    expect(isTrustedSplitStackHostname('8.8.8.8')).toBe(false);
    expect(isTrustedSplitStackHostname('api.openai.com')).toBe(false);
    expect(isTrustedSplitStackHostname('172.15.0.1')).toBe(false);
    expect(isTrustedSplitStackHostname('172.32.0.1')).toBe(false);
  });

  it('correctly evaluates full API URLs for local or split-stack hosting', () => {
    expect(isLoopbackApiUrl('http://127.0.0.1:11434/v1')).toBe(true);
    expect(isLoopbackApiUrl('http://192.168.1.50:11434/v1')).toBe(false);

    expect(isLocalOrTrustedSplitStackApiUrl('http://127.0.0.1:11434/v1')).toBe(true);
    expect(isLocalOrTrustedSplitStackApiUrl('http://192.168.1.50:11434/v1')).toBe(true);
    expect(isLocalOrTrustedSplitStackApiUrl('http://100.80.20.10:8000/v1')).toBe(true);
    expect(isLocalOrTrustedSplitStackApiUrl('http://dgx-spark.local:8000/v1')).toBe(true);
    expect(isLocalOrTrustedSplitStackApiUrl('https://api.openai.com/v1')).toBe(false);
    expect(isLocalOrTrustedSplitStackApiUrl('')).toBe(false);
    expect(isLocalOrTrustedSplitStackApiUrl(null)).toBe(false);
  });

  it('allows no-auth for trusted split-stack endpoints and resolves synthetic marker', () => {
    const lanProvider = {
      id: 'custom_lan',
      providerType: 'openai-like' as const,
      apiUrl: 'http://192.168.1.50:11434/v1',
      apiKeys: [],
    };
    expect(hasUsableProviderAuth(lanProvider)).toBe(true);
    expect(resolveProviderApiKeyForRequests(lanProvider)).toBe(LOCAL_NO_AUTH_API_KEY_MARKER);
  });
});
