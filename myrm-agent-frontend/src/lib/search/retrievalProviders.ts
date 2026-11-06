/**
 * Retrieval service provider catalog (Embedding + Reranker).
 *
 * Defines supported providers and models for Settings → Retrieval.
 * Each provider lists its recommended model first: that entry is the preset used by the quick setup,
 * by the store defaults and when the provider is switched.
 */

export interface ModelOption {
  value: string; // Real model name (not the routed id)
  label: string;
  description?: string;
}

export interface ProviderConfig {
  id: string; // Route prefix
  name: string; // Display name
  models: ModelOption[];
  requiresApiBase?: boolean; // Whether custom API Base is required
  defaultApiBase?: string; // Default API Base
  modelListUrl?: string; // Model list URL for user reference
}

// ==================== Embedding Providers ====================

export const EMBEDDING_PROVIDERS: ProviderConfig[] = [
  {
    id: 'openai',
    name: 'OpenAI',
    modelListUrl: 'https://platform.openai.com/docs/guides/embeddings',
    models: [
      {
        value: 'text-embedding-3-small',
        label: 'text-embedding-3-small',
        description: '1536d, Cost-effective',
      },
      {
        value: 'text-embedding-3-large',
        label: 'text-embedding-3-large',
        description: '3072d, Best performance',
      },
      {
        value: 'text-embedding-ada-002',
        label: 'text-embedding-ada-002',
        description: '1536d, Legacy',
      },
    ],
  },
  {
    id: 'openai_compatible',
    name: 'OpenAI Compatible (兼容)',
    models: [],
    requiresApiBase: true,
  },
  {
    id: 'jina_ai',
    name: 'Jina AI',
    modelListUrl: 'https://jina.ai/embeddings',
    models: [
      {
        value: 'jina-embeddings-v3',
        label: 'jina-embeddings-v3',
        description: '1024d, Multilingual, high performance',
      },
      {
        value: 'jina-embeddings-v2-base-en',
        label: 'jina-embeddings-v2-base-en',
        description: '768d, English only',
      },
    ],
  },
  {
    id: 'cohere',
    name: 'Cohere',
    modelListUrl: 'https://docs.cohere.com/docs/embeddings',
    models: [
      {
        value: 'embed-multilingual-v3.0',
        label: 'embed-multilingual-v3.0',
        description: 'Supports 100+ languages',
      },
      {
        value: 'embed-english-v3.0',
        label: 'embed-english-v3.0',
        description: 'English optimized',
      },
      {
        value: 'embed-english-light-v3.0',
        label: 'embed-english-light-v3.0',
        description: 'Lightweight, faster',
      },
    ],
  },
  {
    id: 'voyage',
    name: 'Voyage AI',
    modelListUrl: 'https://docs.voyageai.com/docs/embeddings',
    models: [
      {
        value: 'voyage-3',
        label: 'voyage-3',
        description: '1024d, Latest generation',
      },
      {
        value: 'voyage-3-lite',
        label: 'voyage-3-lite',
        description: '512d, Lightweight',
      },
      {
        value: 'voyage-code-3',
        label: 'voyage-code-3',
        description: '1024d, Code optimized',
      },
      {
        value: 'voyage-2',
        label: 'voyage-2',
        description: '1024d, Previous generation',
      },
    ],
  },
  {
    id: 'azure',
    name: 'Azure OpenAI',
    modelListUrl: 'https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/models',
    models: [
      {
        value: 'text-embedding-3-small',
        label: 'text-embedding-3-small',
        description: 'Azure deployment',
      },
      {
        value: 'text-embedding-3-large',
        label: 'text-embedding-3-large',
        description: 'Azure deployment',
      },
    ],
  },
  {
    id: 'siliconflow',
    name: 'Silicon Flow（硅基流动）',
    defaultApiBase: 'https://api.siliconflow.cn/v1',
    modelListUrl: 'https://cloud.siliconflow.cn/me/models?types=embedding',
    models: [
      {
        value: 'BAAI/bge-m3',
        label: 'BAAI/bge-m3',
        description: '1024d, Multilingual, 8K tokens, Free',
      },
      {
        value: 'Qwen/Qwen3-Embedding-8B',
        label: 'Qwen/Qwen3-Embedding-8B',
        description: '4096d, 32K tokens, ¥0.28/M',
      },
      {
        value: 'Qwen/Qwen3-Embedding-0.6B',
        label: 'Qwen/Qwen3-Embedding-0.6B',
        description: '1024d, 32K tokens, ¥0.07/M',
      },
      {
        value: 'netease-youdao/bce-embedding-base_v1',
        label: 'netease-youdao/bce-embedding-base_v1',
        description: '768d, Multilingual, 512 tokens, Free',
      },
      {
        value: 'BAAI/bge-large-en-v1.5',
        label: 'BAAI/bge-large-en-v1.5',
        description: '1024d, English, 512 tokens, Free',
      },
      {
        value: 'Qwen/Qwen3-Embedding-4B',
        label: 'Qwen/Qwen3-Embedding-4B',
        description: '2560d, 32K tokens, ¥0.14/M',
      },
      {
        value: 'BAAI/bge-large-zh-v1.5',
        label: 'BAAI/bge-large-zh-v1.5',
        description: '1024d, Chinese, 512 tokens, Free',
      },
      {
        value: 'Pro/BAAI/bge-m3',
        label: 'Pro/BAAI/bge-m3',
        description: '1024d, Multilingual, 8K tokens, ¥0.07/M',
      },
    ],
  },
];

// ==================== Reranker Providers ====================

export const RERANKER_PROVIDERS: ProviderConfig[] = [
  {
    id: 'openai_compatible',
    name: 'OpenAI Compatible (兼容)',
    models: [],
    requiresApiBase: true,
  },
  {
    id: 'cohere',
    name: 'Cohere',
    modelListUrl: 'https://docs.cohere.com/docs/rerank-2',
    models: [
      {
        value: 'rerank-v3.5',
        label: 'rerank-v3.5',
        description: 'Best overall performance',
      },
      {
        value: 'rerank-english-v3.0',
        label: 'rerank-english-v3.0',
        description: 'English optimized',
      },
      {
        value: 'rerank-multilingual-v3.0',
        label: 'rerank-multilingual-v3.0',
        description: 'Supports 100+ languages',
      },
    ],
  },
  {
    id: 'jina_ai',
    name: 'Jina AI',
    modelListUrl: 'https://jina.ai/reranker',
    models: [
      {
        value: 'jina-reranker-v2-base-multilingual',
        label: 'jina-reranker-v2-base-multilingual',
        description: 'Supports 89 languages',
      },
      {
        value: 'jina-reranker-v1-base-en',
        label: 'jina-reranker-v1-base-en',
        description: 'English only',
      },
    ],
  },
  {
    id: 'voyage',
    name: 'Voyage AI',
    modelListUrl: 'https://docs.voyageai.com/docs/reranker',
    models: [
      {
        value: 'rerank-2',
        label: 'rerank-2',
        description: 'Latest generation',
      },
      {
        value: 'rerank-lite-1',
        label: 'rerank-lite-1',
        description: 'Lightweight, faster',
      },
    ],
  },
  {
    id: 'together_ai',
    name: 'Together AI',
    modelListUrl: 'https://docs.together.ai/docs/inference-models',
    models: [
      {
        value: 'Salesforce/Llama-Rank-V1',
        label: 'Llama-Rank-V1',
        description: 'Open source reranker',
      },
    ],
  },
  {
    id: 'siliconflow',
    name: 'Silicon Flow（硅基流动）',
    defaultApiBase: 'https://api.siliconflow.cn/v1',
    modelListUrl: 'https://cloud.siliconflow.cn/me/models?types=reranker',
    models: [
      {
        value: 'BAAI/bge-reranker-v2-m3',
        label: 'BAAI/bge-reranker-v2-m3',
        description: 'Multilingual, high performance',
      },
      {
        value: 'Pro/BAAI/bge-reranker-v2-m3',
        label: 'Pro/BAAI/bge-reranker-v2-m3',
        description: 'Multilingual, enhanced version',
      },
      {
        value: 'netease-youdao/bce-reranker-base_v1',
        label: 'netease-youdao/bce-reranker-base_v1',
        description: 'Multilingual, balanced',
      },
      {
        value: 'Qwen/Qwen3-Reranker-8B',
        label: 'Qwen/Qwen3-Reranker-8B',
        description: 'Latest generation, best performance',
      },
      {
        value: 'Qwen/Qwen3-Reranker-4B',
        label: 'Qwen/Qwen3-Reranker-4B',
        description: 'Balanced performance and speed',
      },
      {
        value: 'Qwen/Qwen3-Reranker-0.6B',
        label: 'Qwen/Qwen3-Reranker-0.6B',
        description: 'Lightweight, fast inference',
      },
    ],
  },
];

// ==================== Presets ====================

/** Provider that new retrieval configurations start on: a hosted service with a multilingual preset for both roles. */
export const DEFAULT_PROVIDER_ID = 'siliconflow';

/** The recommended model of a provider (its first catalog entry); empty where the user types the model name. */
export function getPresetModel(providers: ProviderConfig[], providerId: string): string {
  return providers.find((provider) => provider.id === providerId)?.models[0]?.value ?? '';
}

/**
 * Providers that serve both roles with a preset model each, so one provider and one key set up both.
 * Custom endpoints need their own model names and stay in the advanced configuration.
 */
export const QUICK_SETUP_PROVIDERS: ProviderConfig[] = EMBEDDING_PROVIDERS.filter(
  ({ id }) => getPresetModel(EMBEDDING_PROVIDERS, id) !== '' && getPresetModel(RERANKER_PROVIDERS, id) !== '',
);

// ==================== Helper Functions ====================

/**
 * Convert provider + model to the routed model id.
 *
 * @example
 * toRoutedModelId('openai', 'text-embedding-3-small') → 'text-embedding-3-small'
 * toRoutedModelId('jina_ai', 'jina-embeddings-v3') → 'jina_ai/jina-embeddings-v3'
 * toRoutedModelId('siliconflow', 'BAAI/bge-large-zh-v1.5') → 'openai/BAAI/bge-large-zh-v1.5'
 */
export function toRoutedModelId(providerId: string, modelName: string): string {
  if (providerId === 'openai') {
    return modelName;
  }

  if (providerId === 'siliconflow') {
    return `openai/${modelName}`;
  }

  if (providerId === 'openai_compatible') {
    return `openai/${modelName}`;
  }

  return `${providerId}/${modelName}`;
}
