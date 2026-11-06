import { describe, expect, it } from 'vitest';

import {
  DEFAULT_PROVIDER_ID,
  EMBEDDING_PROVIDERS,
  QUICK_SETUP_PROVIDERS,
  RERANKER_PROVIDERS,
  getPresetModel,
  toLiteLLMFormat,
} from '../retrievalProviders';

describe('toLiteLLMFormat', () => {
  it.each([
    ['openai', 'text-embedding-3-small', 'text-embedding-3-small'],
    ['siliconflow', 'BAAI/bge-m3', 'openai/BAAI/bge-m3'],
    ['openai_compatible', 'my-model', 'openai/my-model'],
    ['jina_ai', 'jina-embeddings-v3', 'jina_ai/jina-embeddings-v3'],
    ['cohere', 'rerank-v3.5', 'cohere/rerank-v3.5'],
  ])('routes %s / %s as %s', (providerId, model, expected) => {
    expect(toLiteLLMFormat(providerId, model)).toBe(expected);
  });
});

describe('preset models', () => {
  it('is the first listed model, and empty where the user types the model name', () => {
    for (const provider of [...EMBEDDING_PROVIDERS, ...RERANKER_PROVIDERS]) {
      expect(getPresetModel([provider], provider.id)).toBe(provider.models[0]?.value ?? '');
    }
  });

  it('starts the default provider on the multilingual models', () => {
    expect(DEFAULT_PROVIDER_ID).toBe('siliconflow');
    expect(getPresetModel(EMBEDDING_PROVIDERS, DEFAULT_PROVIDER_ID)).toBe('BAAI/bge-m3');
    expect(getPresetModel(RERANKER_PROVIDERS, DEFAULT_PROVIDER_ID)).toBe('BAAI/bge-reranker-v2-m3');
  });

  it('presets Cohere to its multilingual embedding rather than the English-only one', () => {
    expect(getPresetModel(EMBEDDING_PROVIDERS, 'cohere')).toBe('embed-multilingual-v3.0');
  });

  it('has no preset for an unknown provider or one that needs a custom model name', () => {
    expect(getPresetModel(EMBEDDING_PROVIDERS, 'unknown')).toBe('');
    expect(getPresetModel(EMBEDDING_PROVIDERS, 'openai_compatible')).toBe('');
  });
});

describe('quick setup providers', () => {
  it('lists the providers that serve both roles from one key', () => {
    expect(QUICK_SETUP_PROVIDERS.map((provider) => provider.id).sort()).toEqual([
      'cohere',
      'jina_ai',
      'siliconflow',
      'voyage',
    ]);
  });

  it('leaves out providers with a single role and the custom endpoint', () => {
    const ids = QUICK_SETUP_PROVIDERS.map((provider) => provider.id);

    expect(ids).not.toContain('openai');
    expect(ids).not.toContain('azure');
    expect(ids).not.toContain('together_ai');
    expect(ids).not.toContain('openai_compatible');
  });

  it('has a preset model for each role of every listed provider', () => {
    for (const { id } of QUICK_SETUP_PROVIDERS) {
      expect(getPresetModel(EMBEDDING_PROVIDERS, id)).not.toBe('');
      expect(getPresetModel(RERANKER_PROVIDERS, id)).not.toBe('');
    }
  });

  it('includes the provider that new configurations start on', () => {
    expect(QUICK_SETUP_PROVIDERS.map((provider) => provider.id)).toContain(DEFAULT_PROVIDER_ID);
  });
});
