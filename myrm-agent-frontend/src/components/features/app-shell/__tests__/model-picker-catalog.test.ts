import { describe, expect, it } from 'vitest';
import type { ModelCapabilities } from '@/services/llm-config';
import type { CustomModelInfo, ProviderConfig } from '@/store/config/providerTypes';
import {
  applyLocalOwnedFallbacks,
  buildPreflightPairs,
  buildPreflightSignature,
  collectLocalCapabilities,
  groupModelsByProvider,
  mapPreflightResults,
  mergeFetchedCapabilities,
  type EnabledModel,
  type ModelCost,
} from '../model-picker-catalog';

function makeProvider(overrides: Partial<ProviderConfig> & { id: string }): ProviderConfig {
  return {
    routingProfile: overrides.id,
    name: overrides.id,
    isBuiltIn: false,
    isEnabled: true,
    apiKeys: [],
    apiUrl: '',
    enabledModels: [],
    availableModels: [],
    ...overrides,
  };
}

const CAPS: ModelCapabilities = {
  supports_vision: false,
  supports_function_calling: true,
  supports_reasoning: false,
  supports_audio_input: false,
  supports_video_input: false,
  supports_web_search: false,
  supports_prompt_caching: false,
  input_cost_per_token: 0.000002,
  output_cost_per_token: 0.000008,
  max_input_tokens: 128_000,
  max_output_tokens: null,
};

const OPENAI = makeProvider({ id: 'openai', name: 'OpenAI', providerType: 'openai-like' });
const OLLAMA = makeProvider({ id: 'ollama', name: 'Ollama' });
const ENABLED: EnabledModel[] = [
  { providerId: 'openai', providerName: 'OpenAI', model: 'gpt-4o' },
  { providerId: 'openai', providerName: 'OpenAI', model: 'o3' },
  { providerId: 'ollama', providerName: 'Ollama', model: 'llama3' },
];

describe('collectLocalCapabilities', () => {
  it('maps custom model info locally and queues the remaining models for a server lookup', () => {
    const customInfo: Record<string, CustomModelInfo> = {
      'openai/o3': {
        source: 'user',
        lastUpdated: '2026-01-01',
        supports_reasoning: true,
        max_input_tokens: 200_000,
        input_cost_per_million: 2,
        output_cost_per_million: 8,
      },
    };

    const { mapped, costs, toFetch, nameMap } = collectLocalCapabilities(ENABLED, [OPENAI, OLLAMA], customInfo);

    expect(mapped.o3).toMatchObject({ supports_reasoning: true, max_input_tokens: 200_000, supports_vision: false });
    expect(costs.o3).toEqual({ input: 2, output: 8 });
    expect(toFetch).toHaveLength(2);
    expect(Object.values(nameMap).sort()).toEqual(['gpt-4o', 'llama3']);
    expect(toFetch.every((liteName) => liteName in nameMap)).toBe(true);
  });
});

describe('mergeFetchedCapabilities', () => {
  it('stores fetched capabilities under the model name and converts per-token prices to per million', () => {
    const mapped: Record<string, ModelCapabilities> = {};
    const costs: Record<string, ModelCost> = {};

    mergeFetchedCapabilities(
      { 'openai/gpt-4o': CAPS },
      ['openai/gpt-4o', 'openai/missing'],
      { 'openai/gpt-4o': 'gpt-4o' },
      mapped,
      costs,
    );

    expect(mapped['gpt-4o']).toBe(CAPS);
    expect(costs['gpt-4o']).toEqual({ input: 2, output: 8 });
    expect(Object.keys(mapped)).toEqual(['gpt-4o']);
  });

  it('keeps capabilities without prices out of the cost map', () => {
    const mapped: Record<string, ModelCapabilities> = {};
    const costs: Record<string, ModelCost> = {};
    const free = { ...CAPS, input_cost_per_token: null, output_cost_per_token: null };

    mergeFetchedCapabilities(
      { 'ollama/llama3': free },
      ['ollama/llama3'],
      { 'ollama/llama3': 'llama3' },
      mapped,
      costs,
    );

    expect(mapped.llama3).toBe(free);
    expect(costs).toEqual({});
  });
});

describe('applyLocalOwnedFallbacks', () => {
  it('prices self-hosted endpoints at zero and leaves hosted and explicitly priced models alone', () => {
    const lmStudio = makeProvider({ id: 'lm_studio', name: 'LM Studio' });
    const models: EnabledModel[] = [...ENABLED, { providerId: 'lm_studio', providerName: 'LM Studio', model: 'qwen' }];
    const costs: Record<string, ModelCost> = { llama3: { input: 0.5, output: 1 } };

    applyLocalOwnedFallbacks(costs, models, [OPENAI, OLLAMA, lmStudio]);

    expect(costs.llama3).toEqual({ input: 0.5, output: 1 });
    expect(costs.qwen).toEqual({ input: 0, output: 0, isLocalOwned: true });
    expect(costs['gpt-4o']).toBeUndefined();
  });

  it('treats loopback API URLs as local', () => {
    const local = makeProvider({ id: 'my-vllm', apiUrl: 'http://localhost:8000/v1' });
    const costs: Record<string, ModelCost> = {};

    applyLocalOwnedFallbacks(costs, [{ providerId: 'my-vllm', providerName: 'vLLM', model: 'qwen' }], [local]);

    expect(costs.qwen).toEqual({ input: 0, output: 0, isLocalOwned: true });
  });
});

describe('groupModelsByProvider', () => {
  const providers = [OPENAI, OLLAMA];
  const costs: Record<string, ModelCost> = { llama3: { input: 0, output: 0, isLocalOwned: true } };

  it('groups all models by provider in first-seen order when the search is empty', () => {
    const groups = groupModelsByProvider(ENABLED, providers, '  ', costs);

    expect(groups.map((g) => [g.provider.id, g.models])).toEqual([
      ['openai', ['gpt-4o', 'o3']],
      ['ollama', ['llama3']],
    ]);
  });

  it('matches model and provider names case-insensitively', () => {
    expect(groupModelsByProvider(ENABLED, providers, 'GPT', costs).map((g) => g.models)).toEqual([['gpt-4o']]);
    expect(groupModelsByProvider(ENABLED, providers, 'ollama', costs).map((g) => g.models)).toEqual([['llama3']]);
    expect(groupModelsByProvider(ENABLED, providers, 'zzz', costs)).toEqual([]);
  });

  it.each(['$0', '0', 'free', 'local', '本地', '免费'])('lists only local-owned models for the %s query', (query) => {
    const groups = groupModelsByProvider(ENABLED, providers, query, costs);

    expect(groups.map((g) => g.models)).toEqual([['llama3']]);
  });

  it('skips models whose provider is no longer configured', () => {
    expect(groupModelsByProvider(ENABLED, [OPENAI], '', costs).map((g) => g.provider.id)).toEqual(['openai']);
  });
});

describe('preflight helpers', () => {
  it('builds candidate pairs only for models with a provider and known capabilities', () => {
    const pairs = buildPreflightPairs(ENABLED, [OPENAI], {
      'gpt-4o': CAPS,
      llama3: CAPS,
      o3: { ...CAPS, max_input_tokens: null },
    });

    expect(pairs.map((p) => [p.providerId, p.model, p.maxInput])).toEqual([
      ['openai', 'gpt-4o', 128_000],
      ['openai', 'o3', null],
    ]);
  });

  it('changes the request signature whenever the session context or candidates change', () => {
    const pairs = buildPreflightPairs(ENABLED, [OPENAI, OLLAMA], { 'gpt-4o': CAPS });
    const base = { chatId: 'c1', estimatedTokens: 1000, compressStartRatio: 0.5, promptMode: 'full', turnCount: 3 };
    const signature = buildPreflightSignature(base, pairs);

    expect(buildPreflightSignature({ ...base }, pairs)).toBe(signature);
    for (const change of [
      { chatId: 'c2' },
      { estimatedTokens: 1001 },
      { compressStartRatio: null },
      { promptMode: 'lean' },
      { turnCount: 4 },
    ]) {
      expect(buildPreflightSignature({ ...base, ...change }, pairs)).not.toBe(signature);
    }
    expect(buildPreflightSignature(base, [])).not.toBe(signature);
  });

  it('re-keys server results from the route name to providerId/model and drops missing ones', () => {
    const pairs = buildPreflightPairs(ENABLED, [OPENAI, OLLAMA], { 'gpt-4o': CAPS, llama3: CAPS });
    const result = {
      model: pairs[0].liteName,
      found: true,
      new_window: 8000,
      compress_threshold: 6000,
      will_compress: true,
    };

    expect(mapPreflightResults(pairs, { [pairs[0].liteName]: result })).toEqual({ 'openai/gpt-4o': result });
  });
});
