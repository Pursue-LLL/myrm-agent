import { describe, it, expect, beforeEach, vi } from 'vitest';
import { getProviderIdFromUrl, findProviderByApiUrl, type ModelsDevApiResponse } from '../models-dev';

const apiRequest = vi.hoisted(() => vi.fn());

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  apiRequest,
}));

// Minimal mock data mimicking models.dev structure
const mockModelsDevData: ModelsDevApiResponse = {
  openai: {
    id: 'openai',
    name: 'OpenAI',
    models: {
      'gpt-4o': { id: 'gpt-4o', name: 'GPT-4o' },
      'gpt-4o-mini': { id: 'gpt-4o-mini', name: 'GPT-4o Mini' },
    },
    // openai has no `api` field in real data
  },
  'alibaba-cn': {
    id: 'alibaba-cn',
    name: 'Alibaba (China)',
    api: 'https://dashscope.aliyuncs.com/compatible-mode/v1',
    models: Object.fromEntries(
      Array.from({ length: 80 }, (_, i) => [`qwen-model-${i}`, { id: `qwen-model-${i}`, name: `Qwen ${i}` }]),
    ),
  },
  'alibaba-coding-plan-cn': {
    id: 'alibaba-coding-plan-cn',
    name: 'Alibaba Coding Plan (China)',
    api: 'https://coding.dashscope.aliyuncs.com/v1',
    models: {
      'MiniMax-M2.5': { id: 'MiniMax-M2.5', name: 'MiniMax M2.5' },
      'qwen3-coder-plus': { id: 'qwen3-coder-plus', name: 'Qwen3 Coder Plus' },
      'kimi-k2.5': { id: 'kimi-k2.5', name: 'Kimi K2.5' },
    },
  },
  deepseek: {
    id: 'deepseek',
    name: 'DeepSeek',
    api: 'https://api.deepseek.com',
    models: {
      'deepseek-chat': { id: 'deepseek-chat', name: 'DeepSeek Chat' },
    },
  },
  'minimax-cn': {
    id: 'minimax-cn',
    name: 'MiniMax (China)',
    api: 'https://api.minimaxi.com/anthropic/v1',
    models: {
      'MiniMax-M2': { id: 'MiniMax-M2', name: 'MiniMax M2' },
      'MiniMax-M2.7': { id: 'MiniMax-M2.7', name: 'MiniMax M2.7' },
    },
  },
  'minimax-cn-coding-plan': {
    id: 'minimax-cn-coding-plan',
    name: 'MiniMax (China) Coding Plan',
    api: 'https://api.minimaxi.com/anthropic/v1',
    models: {
      'MiniMax-M2': { id: 'MiniMax-M2', name: 'MiniMax M2' },
    },
  },
};

describe('getProviderIdFromUrl', () => {
  it('should match exact hostname from static map', () => {
    expect(getProviderIdFromUrl('https://api.openai.com/v1')).toBe('openai');
    expect(getProviderIdFromUrl('https://api.deepseek.com')).toBe('deepseek');
    expect(getProviderIdFromUrl('https://dashscope.aliyuncs.com/compatible-mode/v1')).toBe('alibaba-cn');
    expect(getProviderIdFromUrl('https://ai-gateway.vercel.sh/v1')).toBe('vercel');
  });

  it('should match coding.dashscope precisely', () => {
    expect(getProviderIdFromUrl('https://coding.dashscope.aliyuncs.com/v1')).toBe('alibaba-coding-plan-cn');
    expect(getProviderIdFromUrl('https://coding-intl.dashscope.aliyuncs.com/v1')).toBe('alibaba-coding-plan');
  });

  it('should NOT match subdomain patterns (regression test)', () => {
    // coding.dashscope.aliyuncs.com must NOT match dashscope.aliyuncs.com
    const result = getProviderIdFromUrl('https://coding.dashscope.aliyuncs.com/v1');
    expect(result).not.toBe('alibaba-cn');
  });

  it('should return null for unknown URLs', () => {
    expect(getProviderIdFromUrl('https://my-custom-proxy.com/v1')).toBeNull();
    expect(getProviderIdFromUrl('https://some-random-api.io')).toBeNull();
  });

  it('should return null for invalid input', () => {
    expect(getProviderIdFromUrl('')).toBeNull();
    expect(getProviderIdFromUrl('not-a-url')).toBeNull();
  });
});

describe('findProviderByApiUrl', () => {
  it('should precisely match coding.dashscope to alibaba-coding-plan-cn', () => {
    const result = findProviderByApiUrl(mockModelsDevData, 'https://coding.dashscope.aliyuncs.com/v1');
    expect(result).toBe('alibaba-coding-plan-cn');
  });

  it('should match dashscope.aliyuncs.com to alibaba-cn (more models)', () => {
    const result = findProviderByApiUrl(mockModelsDevData, 'https://dashscope.aliyuncs.com/compatible-mode/v1');
    expect(result).toBe('alibaba-cn');
  });

  it('should match deepseek correctly', () => {
    expect(findProviderByApiUrl(mockModelsDevData, 'https://api.deepseek.com')).toBe('deepseek');
    expect(findProviderByApiUrl(mockModelsDevData, 'https://api.deepseek.com/v1')).toBe('deepseek');
  });

  it('should select provider with most models when hostname collision', () => {
    // api.minimaxi.com has two providers: minimax-cn (2 models) and minimax-cn-coding-plan (1 model)
    const result = findProviderByApiUrl(mockModelsDevData, 'https://api.minimaxi.com/v1');
    expect(result).toBe('minimax-cn');
  });

  it('should return null for providers without api field', () => {
    // openai has no `api` field in models.dev
    const result = findProviderByApiUrl(mockModelsDevData, 'https://api.openai.com/v1');
    expect(result).toBeNull();
  });

  it('should return null for unknown URLs', () => {
    expect(findProviderByApiUrl(mockModelsDevData, 'https://unknown-provider.com/v1')).toBeNull();
  });

  it('should return null for invalid input', () => {
    expect(findProviderByApiUrl(mockModelsDevData, '')).toBeNull();
    expect(findProviderByApiUrl(mockModelsDevData, 'not-a-url')).toBeNull();
  });

  it('should return null for empty data', () => {
    expect(findProviderByApiUrl({}, 'https://api.deepseek.com')).toBeNull();
  });
});

describe('fetchModelsDevData', () => {
  let fetchModelsDevData: typeof import('../models-dev').fetchModelsDevData;

  // The catalog cache lives at module level, so each test starts from a freshly loaded module.
  beforeEach(async () => {
    vi.resetModules();
    apiRequest.mockReset();
    ({ fetchModelsDevData } = await import('../models-dev'));
  });

  it('reads the catalog through the backend proxy without a global error toast', async () => {
    apiRequest.mockResolvedValue(mockModelsDevData);

    await expect(fetchModelsDevData()).resolves.toBe(mockModelsDevData);

    expect(apiRequest).toHaveBeenCalledWith('/integrations/models-dev', { silent: true, timeout: 15_000 });
  });

  it('serves repeated reads from the cache until a refresh is forced', async () => {
    apiRequest.mockResolvedValue(mockModelsDevData);

    await fetchModelsDevData();
    await fetchModelsDevData();
    expect(apiRequest).toHaveBeenCalledTimes(1);

    await fetchModelsDevData(true);
    expect(apiRequest).toHaveBeenCalledTimes(2);
  });

  it('rejects an empty catalog and does not cache it', async () => {
    apiRequest.mockResolvedValueOnce({}).mockResolvedValueOnce(mockModelsDevData);

    await expect(fetchModelsDevData()).rejects.toThrow('models.dev returned empty payload');
    await expect(fetchModelsDevData()).resolves.toBe(mockModelsDevData);
    expect(apiRequest).toHaveBeenCalledTimes(2);
  });

  it('passes a failed request on to the caller', async () => {
    apiRequest.mockRejectedValue(new Error('Failed to fetch models.dev data'));

    await expect(fetchModelsDevData()).rejects.toThrow('Failed to fetch models.dev data');
  });
});
