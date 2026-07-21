// 提供商类型定义

import {
  KNOWN_LITELLM_ROUTE_PREFIXES as _GENERATED_LITELLM_ROUTE_PREFIXES,
  PROVIDER_TO_LITELLM_PREFIX,
} from './litellmRouting.generated';

export { PROVIDER_TO_LITELLM_PREFIX };

// ==================== Provider 分类 ====================

/**
 * Provider 类别
 * - api: API-based providers (OpenAI, Anthropic, etc.)
 * - local: Local providers (Ollama, LM Studio, etc.)
 */
export type ProviderCategory = 'api' | 'local';

/**
 * 判断 Provider 类别
 */
export function getProviderCategory(providerId: string): ProviderCategory {
  // Local providers
  if (['ollama', 'lm_studio'].includes(providerId)) {
    return 'local';
  }
  // 默认为 API provider
  return 'api';
}

// 自定义提供商可选的兼容类型
export const CUSTOM_PROVIDER_TYPES = ['openai-like', 'gemini-like', 'anthropic-like'] as const;

export type CustomProviderType = (typeof CUSTOM_PROVIDER_TYPES)[number];

// 自定义提供商类型信息
export interface CustomProviderTypeInfo {
  id: CustomProviderType;
  name: string;
  defaultApiUrl: string;
  litellmPrefix: string;
}

// 自定义提供商类型配置
export const CUSTOM_PROVIDER_TYPE_INFO: Record<CustomProviderType, CustomProviderTypeInfo> = {
  'openai-like': {
    id: 'openai-like',
    name: 'OpenAI-Like',
    defaultApiUrl: 'https://api.openai.com/v1',
    litellmPrefix: 'openai',
  },
  'gemini-like': {
    id: 'gemini-like',
    name: 'Gemini-Like',
    defaultApiUrl: 'https://generativelanguage.googleapis.com/v1beta',
    litellmPrefix: 'gemini',
  },
  'anthropic-like': {
    id: 'anthropic-like',
    name: 'Anthropic-Like',
    defaultApiUrl: 'https://api.anthropic.com',
    litellmPrefix: 'anthropic',
  },
};

/** Resolve custom provider compat metadata; ignores legacy/invalid providerType values. */
export function resolveCustomProviderTypeInfo(
  providerType?: string,
): CustomProviderTypeInfo | undefined {
  if (!providerType || !CUSTOM_PROVIDER_TYPES.includes(providerType as CustomProviderType)) {
    return undefined;
  }
  return CUSTOM_PROVIDER_TYPE_INFO[providerType as CustomProviderType];
}

/** Known LiteLLM route segments (longest first; generated list plus custom compat prefixes). */
const KNOWN_LITELLM_ROUTE_PREFIXES: readonly string[] = (() => {
  const litellmPrefixesFromCustom = Object.values(CUSTOM_PROVIDER_TYPE_INFO).map((t) => t.litellmPrefix);
  return [...new Set([..._GENERATED_LITELLM_ROUTE_PREFIXES, ...litellmPrefixesFromCustom])].sort(
    (a, b) => b.length - a.length,
  );
})();

// 内置提供商 ID
export const BUILT_IN_PROVIDERS = [
  'openai',
  'anthropic',
  'gemini',
  'deepseek',
  'openrouter',
  'zai',
  'xai',
  'ollama',
  'moonshot',
  'lm_studio',
  'groq',
  'dashscope',
  'minimax',
  'mistral',
  'together_ai',
  'siliconflow',
  'volcengine',
  'fireworks_ai',
  'azure',
  'spark',
  'perplexity',
  'jina_ai',
  'bedrock',
  'xiaomi_mimo',
  'nvidia',
  'ai302',
] as const;

export type BuiltInProviderId = (typeof BUILT_IN_PROVIDERS)[number];

// 备选 API URL 配置
export interface AlternativeApiUrl {
  url: string;
  label: string; // 显示名称，如 "Global (海外版)"
}

// 提供商信息
export interface ProviderInfo {
  id: string;
  name: string;
  icon?: string;
  isBuiltIn: boolean;
  defaultApiUrl?: string;
  alternativeApiUrls?: AlternativeApiUrl[]; // 可选的备选地址列表
}

// 内置提供商配置
export const BUILT_IN_PROVIDER_INFO: Record<BuiltInProviderId, ProviderInfo> = {
  openai: {
    id: 'openai',
    name: 'OpenAI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.openai.com/v1',
  },
  anthropic: {
    id: 'anthropic',
    name: 'Anthropic',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.anthropic.com',
  },
  gemini: {
    id: 'gemini',
    name: 'Google Gemini',
    isBuiltIn: true,
    defaultApiUrl: 'https://generativelanguage.googleapis.com/v1beta',
  },
  deepseek: {
    id: 'deepseek',
    name: 'DeepSeek',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.deepseek.com',
  },
  openrouter: {
    id: 'openrouter',
    name: 'OpenRouter',
    isBuiltIn: true,
    defaultApiUrl: 'https://openrouter.ai/api/v1',
  },
  zai: {
    id: 'zai',
    name: 'Z.AI (Zhipu AI)',
    isBuiltIn: true,
    defaultApiUrl: 'https://open.bigmodel.cn/api/paas/v4',
    alternativeApiUrls: [
      { url: 'https://open.bigmodel.cn/api/paas/v4', label: 'China (国内版)' },
      { url: 'https://api.z.ai/api/paas/v4', label: 'International (国际版)' },
      { url: 'https://api.z.ai/api/coding/paas/v4', label: 'Coding Plan' },
    ],
  },
  xai: {
    id: 'xai',
    name: 'xAI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.x.ai/v1',
  },
  ollama: {
    id: 'ollama',
    name: 'Ollama',
    isBuiltIn: true,
    defaultApiUrl: 'http://localhost:11434',
  },
  moonshot: {
    id: 'moonshot',
    name: 'Moonshot AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.moonshot.cn/v1',
    alternativeApiUrls: [
      { url: 'https://api.moonshot.cn/v1', label: 'China (国内版)' },
      { url: 'https://api.moonshot.ai/v1', label: 'International (国际版)' },
    ],
  },
  lm_studio: {
    id: 'lm_studio',
    name: 'LM Studio',
    isBuiltIn: true,
    defaultApiUrl: 'http://localhost:1234/v1',
  },
  groq: {
    id: 'groq',
    name: 'Groq',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.groq.com/openai/v1',
  },
  dashscope: {
    id: 'dashscope',
    name: 'Dashscope (Qwen)',
    isBuiltIn: true,
    defaultApiUrl: 'https://coding.dashscope.aliyuncs.com/v1',
    alternativeApiUrls: [
      { url: 'https://coding.dashscope.aliyuncs.com/v1', label: 'China (国内版)' },
      { url: 'https://dashscope-intl.aliyuncs.com/compatible-mode/v1', label: 'International (国际版)' },
    ],
  },
  minimax: {
    id: 'minimax',
    name: 'MiniMax',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.minimaxi.com/v1',
    alternativeApiUrls: [
      { url: 'https://api.minimaxi.com/v1', label: 'China (国内版)' },
      { url: 'https://api.minimax.io/v1', label: 'Global (海外版)' },
    ],
  },
  mistral: {
    id: 'mistral',
    name: 'Mistral AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.mistral.ai/v1',
  },
  together_ai: {
    id: 'together_ai',
    name: 'Together AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.together.xyz/v1',
  },
  siliconflow: {
    id: 'siliconflow',
    name: 'SiliconFlow',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.siliconflow.cn/v1',
    alternativeApiUrls: [
      { url: 'https://api.siliconflow.cn/v1', label: 'China (国内版)' },
      { url: 'https://api.siliconflow.com/v1', label: 'International (国际版)' },
    ],
  },
  volcengine: {
    id: 'volcengine',
    name: 'Doubao (Volcengine)',
    isBuiltIn: true,
    defaultApiUrl: 'https://ark.cn-beijing.volces.com/api/v3',
  },
  fireworks_ai: {
    id: 'fireworks_ai',
    name: 'Fireworks AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.fireworks.ai/inference/v1',
  },
  azure: {
    id: 'azure',
    name: 'Azure OpenAI',
    isBuiltIn: true,
    defaultApiUrl: 'https://{your-resource}.openai.azure.com',
  },
  spark: {
    id: 'spark',
    name: 'Spark (iFlytek)',
    isBuiltIn: true,
    defaultApiUrl: 'https://spark-api-open.xf-yun.com/v1',
  },
  perplexity: {
    id: 'perplexity',
    name: 'Perplexity AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.perplexity.ai',
  },
  jina_ai: {
    id: 'jina_ai',
    name: 'Jina AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.jina.ai',
  },
  bedrock: {
    id: 'bedrock',
    name: 'AWS Bedrock',
    isBuiltIn: true,
    defaultApiUrl: 'https://bedrock-runtime.{region}.amazonaws.com',
  },
  xiaomi_mimo: {
    id: 'xiaomi_mimo',
    name: 'Xiaomi MiMo',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.xiaomimimo.com/v1',
    alternativeApiUrls: [
      { url: 'https://api.xiaomimimo.com/v1', label: 'Standard (标准版)' },
      { url: 'https://token-plan-cn.xiaomimimo.com/v1', label: 'Token Plan (China 国内)' },
      { url: 'https://token-plan-ams.xiaomimimo.com/v1', label: 'Token Plan (Europe 欧洲)' },
      { url: 'https://token-plan-sgp.xiaomimimo.com/v1', label: 'Token Plan (Singapore 新加坡)' },
    ],
  },
  nvidia: {
    id: 'nvidia',
    name: 'Nvidia NIM',
    isBuiltIn: true,
    defaultApiUrl: 'https://integrate.api.nvidia.com/v1',
  },
  ai302: {
    id: 'ai302',
    name: '302.AI',
    isBuiltIn: true,
    defaultApiUrl: 'https://api.302.ai/v1',
  },
};

// 获取 LiteLLM 模型全名
export const getLiteLLMModelName = (
  providerId: string,
  modelName: string,
  providerType?: CustomProviderType,
): string => {
  const normalizedModelName = modelName.toLowerCase();
  for (const routePrefix of KNOWN_LITELLM_ROUTE_PREFIXES) {
    if (normalizedModelName.startsWith(`${routePrefix}/`)) {
      return modelName;
    }
  }

  if (providerType && !CUSTOM_PROVIDER_TYPES.includes(providerType as CustomProviderType)) {
    // 如果 providerType 不是自定义类型，则忽略它，使用 providerId
    providerType = undefined;
  }
  if (providerType) {
    const typeInfo = CUSTOM_PROVIDER_TYPE_INFO[providerType];
    if (normalizedModelName.startsWith(`${typeInfo.litellmPrefix}/`)) {
      return modelName;
    }
    return `${typeInfo.litellmPrefix}/${modelName}`;
  }
  const prefix = PROVIDER_TO_LITELLM_PREFIX[providerId] || providerId;
  if (normalizedModelName.startsWith(`${prefix}/`)) {
    return modelName;
  }
  return `${prefix}/${modelName}`;
};

// API 密钥配置
export interface ApiKeyConfig {
  id: string;
  key: string;
  remark: string;
  isActive: boolean;
}

export type CredentialPoolStrategy = 'round_robin' | 'fill_first' | 'least_used' | 'random';

// 提供商配置
export interface ProviderConfig {
  id: string;
  /** LiteLLM routing segment (may differ from id for multi-gateway OpenAI-compat vendors). */
  routingProfile: string;
  name: string;
  isBuiltIn: boolean;
  isEnabled: boolean;
  apiKeys: ApiKeyConfig[];
  apiUrl: string;
  enabledModels: string[];
  availableModels: string[];
  providerType?: CustomProviderType;
  credentialPoolStrategy?: CredentialPoolStrategy;
}

export const LOCAL_NO_AUTH_API_KEY_MARKER = '__myrm_local_no_auth__';

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname.toLowerCase().trim();
  if (normalized === 'localhost') return true;
  if (normalized === '127.0.0.1') return true;
  if (normalized === '::1' || normalized === '[::1]') return true;
  if (normalized === '0.0.0.0') return true;
  return false;
}

export const isLoopbackApiUrl = (apiUrl?: string | null): boolean => {
  if (!apiUrl) return false;
  const trimmed = apiUrl.trim();
  if (!trimmed) return false;
  const candidate = trimmed.includes('://') ? trimmed : `http://${trimmed}`;
  try {
    const parsed = new URL(candidate);
    return isLoopbackHostname(parsed.hostname);
  } catch {
    return false;
  }
};

export const hasActiveApiKey = (provider: Pick<ProviderConfig, 'apiKeys'>): boolean => {
  return provider.apiKeys?.some((k) => k.isActive && k.key) ?? false;
};

export const supportsProviderNoAuth = (
  provider: Pick<ProviderConfig, 'id' | 'providerType' | 'apiUrl'>,
): boolean => {
  if (provider.id === 'ollama' || provider.id === 'lm_studio') {
    return true;
  }
  if (provider.providerType === 'openai-like' && isLoopbackApiUrl(provider.apiUrl)) {
    return true;
  }
  return false;
};

export const hasUsableProviderAuth = (
  provider: Pick<ProviderConfig, 'id' | 'providerType' | 'apiUrl' | 'apiKeys'>,
): boolean => {
  return hasActiveApiKey(provider) || supportsProviderNoAuth(provider);
};

export const resolveProviderApiKeyForRequests = (
  provider: Pick<ProviderConfig, 'id' | 'providerType' | 'apiUrl' | 'apiKeys'>,
): string | undefined => {
  const active = provider.apiKeys.find((k) => k.isActive && k.key)?.key;
  if (active) return active;
  if (supportsProviderNoAuth(provider)) return LOCAL_NO_AUTH_API_KEY_MARKER;
  return undefined;
};

// 单模型选择配置
export interface SingleModelSelection {
  providerId: string;
  model: string;
}

// 自定义模型信息
export interface CustomModelInfo {
  source: 'api' | 'user';
  lastUpdated: string;
  max_input_tokens?: number;
  /** Cost per million input tokens (USD). Matches models.dev convention. */
  input_cost_per_million?: number;
  /** Cost per million output tokens (USD). Matches models.dev convention. */
  output_cost_per_million?: number;
  supports_vision?: boolean;
  supports_function_calling?: boolean;
  supports_reasoning?: boolean;
  supports_audio_input?: boolean;
  supports_video_input?: boolean;
  temperature?: number;
  extraParams?: Record<string, unknown>;
}

// 模型槽位：主模型 + 可选备用模型
export interface ModelSlot {
  primary: SingleModelSelection | null;
  fallback: SingleModelSelection | null;
  temperature?: number;
  modelKwargs?: Record<string, unknown>;
}

// 智能路由配置：根据任务复杂度自动选择模型层级
export interface RoutingConfig {
  enabled: boolean;
  lightModel: ModelSlot;
  reasoningModel: ModelSlot;
}

// 默认模型配置
export interface DefaultModelConfig {
  baseModel: ModelSlot;
  liteModel: ModelSlot;
  fastModeModel: ModelSlot | null;
  routingConfig: RoutingConfig | null;
  visionFallbackModel?: SingleModelSelection | null;
}

// 初始化默认提供商配置
export const getInitialProviders = (): ProviderConfig[] => {
  return BUILT_IN_PROVIDERS.map((id) => {
    const info = BUILT_IN_PROVIDER_INFO[id];
    return {
      id: info.id,
      name: info.name,
      isBuiltIn: true,
      isEnabled: false,
      apiKeys: [],
      apiUrl: info.defaultApiUrl || '',
      enabledModels: [],
      availableModels: [],
      routingProfile: PROVIDER_TO_LITELLM_PREFIX[id] ?? id,
    };
  });
};

// 初始化默认模型配置
export const getInitialDefaultModelConfig = (): DefaultModelConfig => ({
  baseModel: {
    primary: null,
    fallback: null,
    temperature: 0.7,
    modelKwargs: {},
  },
  liteModel: {
    primary: null,
    fallback: null,
  },
  fastModeModel: null,
  routingConfig: null,
  visionFallbackModel: null,
});

/**
 * 规范化 API URL
 * 用户可能填入具体端点（如 /v1/chat/completions），需要截取 base URL
 *
 * 例如：
 *   https://api.svips.org/v1/chat/completions → https://api.svips.org/v1
 *   https://api.openai.com/v1/chat/completions → https://api.openai.com/v1
 *   https://api.openai.com/v1 → https://api.openai.com/v1 (不变)
 */
export const normalizeApiUrl = (url: string): string => {
  if (!url) return url;

  const normalized = url.replace(/\/+$/, '');

  // 已知的端点路径，需要截取
  const endpointPatterns = ['/chat/completions', '/completions', '/embeddings', '/models'];

  for (const pattern of endpointPatterns) {
    if (normalized.endsWith(pattern)) {
      return normalized.slice(0, -pattern.length);
    }
  }

  return normalized;
};
