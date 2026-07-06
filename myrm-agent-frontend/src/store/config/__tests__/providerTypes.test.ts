import { describe, expect, it } from 'vitest';
import { BUILT_IN_PROVIDER_INFO, getInitialProviders, getLiteLLMModelName, resolveCustomProviderTypeInfo } from '../providerTypes';

describe('providerTypes defaults', () => {
  it('uses the official Xiaomi MiMo API endpoint', () => {
    expect(BUILT_IN_PROVIDER_INFO.xiaomi_mimo.defaultApiUrl).toBe('https://api.xiaomimimo.com/v1');
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
