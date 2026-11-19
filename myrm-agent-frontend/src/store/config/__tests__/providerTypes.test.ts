import { describe, expect, it } from 'vitest';
import { BUILT_IN_PROVIDER_INFO } from '../providerCatalog';
import {
  getInitialProviders,
  getRoutedModelName,
  hasActiveApiKey,
  hasUsableProviderAuth,
  LOCAL_NO_AUTH_API_KEY_MARKER,
  OAUTH_AUTH_API_KEY_MARKER,
  resolveCustomProviderTypeInfo,
  resolveProviderApiKeyForRequests,
} from '../providerTypes';

describe('providerTypes defaults', () => {
  it('uses the official Xiaomi MiMo API endpoint', () => {
    expect(BUILT_IN_PROVIDER_INFO.xiaomi_mimo.defaultApiUrl).toBe('https://api.xiaomimimo.com/v1');
  });

  it('uses the OpenCode Go subscription API endpoint', () => {
    expect(BUILT_IN_PROVIDER_INFO.opencode_go.defaultApiUrl).toBe('https://opencode.ai/zen/go/v1');
    expect(BUILT_IN_PROVIDER_INFO.opencode_go.dashboardUrl).toBe('https://opencode.ai');
    expect(BUILT_IN_PROVIDER_INFO.opencode_go.alternativeApiUrls).toEqual([
      { url: 'https://opencode.ai/zen/go/v1', label: 'Zen / Go (订阅/贡献者套餐)' },
      { url: 'https://opencode.ai/v1', label: 'Standard API (平台标准直连)' },
    ]);
    expect(getRoutedModelName('opencode_go', 'deepseek-v4-flash')).toBe('openai/deepseek-v4-flash');
  });

  it('offers AWS Bedrock with its regional runtime endpoint and routes every model id through the bedrock route', () => {
    expect(BUILT_IN_PROVIDER_INFO.bedrock).toMatchObject({
      name: 'AWS Bedrock',
      isBuiltIn: true,
      defaultApiUrl: 'https://bedrock-runtime.{region}.amazonaws.com',
    });
    expect(getRoutedModelName('bedrock', 'us.anthropic.claude-sonnet-4-5-20250929-v1:0')).toBe(
      'bedrock/us.anthropic.claude-sonnet-4-5-20250929-v1:0',
    );
    expect(getRoutedModelName('bedrock', 'bedrock/amazon.nova-pro-v1:0')).toBe('bedrock/amazon.nova-pro-v1:0');
    expect(
      getRoutedModelName('bedrock', 'arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/abc123'),
    ).toBe('bedrock/arn:aws:bedrock:us-east-1:123456789012:application-inference-profile/abc123');
    expect(getInitialProviders().some((provider) => provider.id === 'bedrock')).toBe(true);
  });

  it('seeds initial Xiaomi provider config with the same endpoint', () => {
    const xiaomiProvider = getInitialProviders().find((provider) => provider.id === 'xiaomi_mimo');

    expect(xiaomiProvider?.apiUrl).toBe('https://api.xiaomimimo.com/v1');
  });

  it('does not double-prefix Xiaomi MiMo when model already includes the route segment', () => {
    expect(getRoutedModelName('xiaomi_mimo', 'mimo-v2-flash')).toBe('xiaomi_mimo/mimo-v2-flash');
    expect(getRoutedModelName('xiaomi_mimo', 'xiaomi_mimo/mimo-v2-flash')).toBe('xiaomi_mimo/mimo-v2-flash');
  });

  it('prefers an already-qualified model id over a mismatched providerId', () => {
    expect(getRoutedModelName('openai', 'xiaomi_mimo/mimo-v2-flash')).toBe('xiaomi_mimo/mimo-v2-flash');
  });

  it('routes a custom provider through the route named by its providerType', () => {
    // A custom OpenAI-compatible row has no generated id mapping; its providerType names the route.
    expect(getRoutedModelName('openai-like', 'muse-spark-1.3-contributor', 'openai')).toBe(
      'openai/muse-spark-1.3-contributor',
    );
  });

  it('keeps the built-in id mapping authoritative over a legacy providerType', () => {
    expect(getRoutedModelName('deepseek', 'deepseek-chat', 'openai')).toBe('deepseek/deepseek-chat');
    expect(getRoutedModelName('minimax', 'MiniMax-M3.1-Flash', 'minimax')).toBe('minimax/MiniMax-M3.1-Flash');
  });

  it('falls back to the provider id when no route can be derived', () => {
    expect(getRoutedModelName('my-private-gateway', 'model-x')).toBe('my-private-gateway/model-x');
  });

  it('correctly configures and routes Vercel AI Gateway without vendor prefix hijacking', () => {
    expect(BUILT_IN_PROVIDER_INFO.vercel_ai_gateway.defaultApiUrl).toBe('https://ai-gateway.vercel.sh/v1');
    expect(getRoutedModelName('vercel_ai_gateway', 'anthropic/claude-3-5-sonnet')).toBe(
      'vercel_ai_gateway/anthropic/claude-3-5-sonnet',
    );
    expect(getRoutedModelName('vercel_ai_gateway', 'openai/gpt-4o')).toBe('vercel_ai_gateway/openai/gpt-4o');
    expect(getRoutedModelName('vercel_ai_gateway', 'meta-llama/llama-3.3-70b')).toBe(
      'vercel_ai_gateway/meta-llama/llama-3.3-70b',
    );
    expect(getRoutedModelName('vercel_ai_gateway', 'vercel_ai_gateway/anthropic/claude-3-5-sonnet')).toBe(
      'vercel_ai_gateway/anthropic/claude-3-5-sonnet',
    );
  });
});

describe('resolveCustomProviderTypeInfo', () => {
  it('returns metadata for valid custom provider types', () => {
    expect(resolveCustomProviderTypeInfo('openai-like')?.routePrefix).toBe('openai');
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

describe('synthetic credential markers', () => {
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

  it('recognizes oauthConnected providers as usable auth and resolves synthetic oauth marker', () => {
    const oauthProvider = {
      id: 'xai',
      providerType: 'openai-like' as const,
      apiUrl: 'https://api.x.ai/v1',
      apiKeys: [],
      oauthConnected: true,
    };
    expect(hasUsableProviderAuth(oauthProvider)).toBe(true);
    expect(resolveProviderApiKeyForRequests(oauthProvider)).toBe(OAUTH_AUTH_API_KEY_MARKER);
  });
});
