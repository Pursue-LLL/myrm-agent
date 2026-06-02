/**
 * 检索服务提供商配置
 *
 * 定义 Embedding 和 Reranker 支持的提供商及其模型
 */

export interface ModelOption {
  value: string; // 真实模型名（非 LiteLLM 格式）
  label: string;
  description?: string;
}

export interface ProviderConfig {
  id: string; // LiteLLM provider prefix
  name: string; // 显示名称
  models: ModelOption[];
  requiresApiBase?: boolean; // 是否需要自定义 API Base
  defaultApiBase?: string; // 默认 API Base
  modelListUrl?: string; // 模型列表网址（供用户参考）
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
        value: 'embed-english-v3.0',
        label: 'embed-english-v3.0',
        description: 'English optimized',
      },
      {
        value: 'embed-multilingual-v3.0',
        label: 'embed-multilingual-v3.0',
        description: 'Supports 100+ languages',
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
        value: 'BAAI/bge-m3',
        label: 'BAAI/bge-m3',
        description: '1024d, Multilingual, 8K tokens, Free',
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

// ==================== Helper Functions ====================

/**
 * 将 provider + model 转换为 LiteLLM 格式
 *
 * @example
 * toLiteLLMFormat('openai', 'text-embedding-3-small') → 'text-embedding-3-small'
 * toLiteLLMFormat('jina_ai', 'jina-embeddings-v3') → 'jina_ai/jina-embeddings-v3'
 * toLiteLLMFormat('siliconflow', 'BAAI/bge-large-zh-v1.5') → 'openai/BAAI/bge-large-zh-v1.5'
 */
export function toLiteLLMFormat(providerId: string, modelName: string): string {
  // OpenAI 是默认 provider，不需要前缀
  if (providerId === 'openai') {
    return modelName;
  }

  // SiliconFlow 使用 openai/ 前缀（兼容 OpenAI API）
  if (providerId === 'siliconflow') {
    return `openai/${modelName}`;
  }

  // OpenAI Compatible 使用 openai/ 前缀
  if (providerId === 'openai_compatible') {
    return `openai/${modelName}`;
  }

  // 其他 provider 使用 provider/model 格式
  return `${providerId}/${modelName}`;
}

/**
 * 从 LiteLLM 格式解析 provider 和 model
 *
 * @example
 * fromLiteLLMFormat('text-embedding-3-small') → { provider: 'openai', model: 'text-embedding-3-small' }
 * fromLiteLLMFormat('jina_ai/jina-embeddings-v3') → { provider: 'jina_ai', model: 'jina-embeddings-v3' }
 * fromLiteLLMFormat('openai/BAAI/bge-large-zh-v1.5') → { provider: 'siliconflow', model: 'BAAI/bge-large-zh-v1.5' }
 */
export function fromLiteLLMFormat(litellmModel: string): { provider: string; model: string } {
  if (!litellmModel.includes('/')) {
    // 没有斜杠，默认是 OpenAI
    return { provider: 'openai', model: litellmModel };
  }

  const [provider, ...modelParts] = litellmModel.split('/');
  const model = modelParts.join('/'); // 处理模型名中可能包含斜杠的情况

  // SiliconFlow 模型特征：openai/ 前缀 + 特殊模型名
  if (
    provider === 'openai' &&
    (model.startsWith('BAAI/') ||
      model.startsWith('Qwen/') ||
      model.startsWith('Pro/') ||
      model.includes('youdao') ||
      model.includes('netease'))
  ) {
    return { provider: 'siliconflow', model };
  }

  // OpenAI Compatible 使用 openai/ 前缀（且模型名包含斜杠）
  if (provider === 'openai' && model.includes('/')) {
    return { provider: 'openai_compatible', model };
  }

  return { provider, model };
}
