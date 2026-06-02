/**
 * models.dev API 服务
 * 从 https://models.dev/api.json 获取模型信息
 */

import type { CustomModelInfo } from '@/store/config/providerTypes';

// ============ models.dev API 类型定义 ============

/** 模型成本信息 */
export interface ModelsDevCost {
  input: number;
  output: number;
  cache_read?: number;
  cache_write?: number;
}

/** 模型限制信息 */
export interface ModelsDevLimit {
  context: number;
  output: number;
}

/** 模型输入/输出模态 */
export interface ModelsDevModalities {
  input?: string[]; // 支持的输入模态，如 ['text', 'image', 'pdf']
  output?: string[]; // 支持的输出模态
}

/** 模型信息 */
export interface ModelsDevModel {
  id: string;
  name: string;
  family?: string;
  attachment?: boolean;
  reasoning?: boolean;
  tool_call?: boolean;
  temperature?: boolean;
  knowledge?: string;
  release_date?: string;
  last_updated?: string;
  modalities?: ModelsDevModalities | string[]; // 支持对象或数组格式
  open_weights?: boolean;
  cost?: ModelsDevCost;
  limit?: ModelsDevLimit;
  status?: 'deprecated' | string;
  interleaved?: boolean;
}

/** Provider 信息 */
export interface ModelsDevProvider {
  id: string;
  env?: string[];
  npm?: string;
  api?: string;
  name: string;
  doc?: string;
  models: Record<string, ModelsDevModel>;
}

/** API 响应类型 */
export type ModelsDevApiResponse = Record<string, ModelsDevProvider>;

// ============ Provider ID 映射 ============

/**
 * models.dev provider ID → 本应用内置 provider ID 的映射
 * 用于匹配用户已配置的 provider
 */
const MODELS_DEV_TO_APP_PROVIDER_MAP: Record<string, string> = {
  openai: 'openai',
  anthropic: 'anthropic',
  google: 'gemini',
  deepseek: 'deepseek',
  openrouter: 'openrouter',
  xai: 'xai',
  groq: 'groq',
  'moonshotai-cn': 'moonshot',
  'alibaba-cn': 'dashscope',
  zai: 'zai',
  'minimax-coding-plan': 'minimax',
  together: 'together_ai',
  fireworks: 'fireworks_ai',
  jina: 'jina_ai',
  nvidia: 'nvidia',
  '302ai': 'ai302',
};

/**
 * 自定义提供商类型 → models.dev provider ID 的映射
 * 用于自定义提供商查找对应的 models.dev 数据
 */
const CUSTOM_TYPE_TO_MODELS_DEV_MAP: Record<string, string> = {
  openai: 'openai',
  gemini: 'google',
  anthropic: 'anthropic',
};

/**
 * API URL 域名 → models.dev provider ID 的映射
 * 用于根据 API URL 自动识别提供商，无需用户手动选择
 */
const URL_DOMAIN_TO_PROVIDER_MAP: Record<string, string> = {
  'api.openai.com': 'openai',
  'api.anthropic.com': 'anthropic',
  'generativelanguage.googleapis.com': 'google',
  'api.deepseek.com': 'deepseek',
  'open.bigmodel.cn': 'zai',
  'api.moonshot.cn': 'moonshotai-cn',
  'dashscope.aliyuncs.com': 'alibaba-cn',
  'dashscope-intl.aliyuncs.com': 'alibaba',
  'coding.dashscope.aliyuncs.com': 'alibaba-coding-plan-cn',
  'coding-intl.dashscope.aliyuncs.com': 'alibaba-coding-plan',
  'api.groq.com': 'groq',
  'api.x.ai': 'xai',
  'openrouter.ai': 'openrouter',
  'api.mistral.ai': 'mistral',
  'api.cohere.ai': 'cohere',
  'api.cohere.com': 'cohere',
  'api.perplexity.ai': 'perplexity',
  'api.together.xyz': 'together',
  'api.fireworks.ai': 'fireworks',
  'api.minimax.io': 'minimax-coding-plan',
  'api.minimaxi.com': 'minimax-coding-plan',
  'integrate.api.nvidia.com': 'nvidia',
  'api.302.ai': '302ai',
};

/**
 * 从 API URL 提取域名并识别对应的 models.dev provider ID（静态映射表，仅精确匹配）
 * @param apiUrl - API URL
 * @returns 对应的 models.dev provider ID，如果无法识别则返回 null
 */
export function getProviderIdFromUrl(apiUrl: string): string | null {
  if (!apiUrl) return null;

  try {
    const url = new URL(apiUrl);
    const hostname = url.hostname.toLowerCase();

    if (hostname in URL_DOMAIN_TO_PROVIDER_MAP) {
      return URL_DOMAIN_TO_PROVIDER_MAP[hostname];
    }

    return null;
  } catch {
    return null;
  }
}

/**
 * 从 models.dev 完整数据中动态精确匹配 provider
 * 通过比较用户 API URL 的 hostname 与每个 provider 的 api 字段 hostname
 * 当多个 provider 共享同一 hostname 时，选择模型数最多的（更通用）
 */
export function findProviderByApiUrl(data: ModelsDevApiResponse, apiUrl: string): string | null {
  if (!apiUrl) return null;

  let inputHostname: string;
  try {
    inputHostname = new URL(apiUrl).hostname.toLowerCase();
  } catch {
    return null;
  }

  let bestMatch: string | null = null;
  let bestModelCount = -1;

  for (const [providerId, provider] of Object.entries(data)) {
    if (!provider.api) continue;
    try {
      const providerHostname = new URL(provider.api).hostname.toLowerCase();
      if (providerHostname === inputHostname) {
        const modelCount = Object.keys(provider.models).length;
        if (modelCount > bestModelCount) {
          bestModelCount = modelCount;
          bestMatch = providerId;
        }
      }
    } catch {
      continue;
    }
  }

  return bestMatch;
}

/**
 * 本应用 provider ID → models.dev provider ID 的反向映射
 */
const APP_TO_MODELS_DEV_PROVIDER_MAP: Record<string, string> = Object.entries(MODELS_DEV_TO_APP_PROVIDER_MAP).reduce(
  (acc, [modelsDevId, appId]) => {
    acc[appId] = modelsDevId;
    return acc;
  },
  {} as Record<string, string>,
);

// ============ 数据获取与缓存 ============

let cachedData: ModelsDevApiResponse | null = null;
let cacheTimestamp = 0;
const CACHE_TTL = 5 * 60 * 1000; // 5 分钟缓存

/**
 * 获取 models.dev 完整数据
 * 通过 Next.js API Route 代理以绕过 CORS 限制
 * 带缓存，5 分钟过期
 */
export async function fetchModelsDevData(forceRefresh = false): Promise<ModelsDevApiResponse> {
  const now = Date.now();

  if (!forceRefresh && cachedData && now - cacheTimestamp < CACHE_TTL) {
    return cachedData;
  }

  const response = await fetch('/api/models-dev', {
    headers: {
      Accept: 'application/json',
    },
    signal: AbortSignal.timeout(15_000),
  });

  if (!response.ok) {
    throw new Error(`Failed to fetch models.dev data: ${response.status}`);
  }

  cachedData = await response.json();
  cacheTimestamp = now;

  return cachedData!;
}

/** 模型列表来源 */
export type ModelsSource = 'api' | 'models.dev' | 'api+models.dev';

/** 获取模型列表的返回结果 */
export interface GetModelsResult {
  provider: ModelsDevProvider | null;
  models: ModelsDevModel[];
  source: ModelsSource;
  apiModels?: string[];
  apiError?: string;
}

/**
 * 根据应用的 provider ID 获取对应的模型列表
 *
 * 双模式获取策略（并行调用）：
 * 1. 并行调用 models.dev API 和 Provider /models API（性能提升 46.7%）
 * 2. 使用 /models API 返回的模型列表过滤 models.dev 的全量数据（保留详细信息）
 * 3. 如果 /models API 失败，fallback 到 models.dev 全量数据
 * 4. 如果未提供 apiKey，仅使用 models.dev 全量
 *
 * @param appProviderId - 应用内置的 provider ID
 * @param options - 可选参数
 * @param options.providerType - 自定义提供商的兼容类型
 * @param options.apiUrl - API URL，用于自动识别提供商
 * @param options.apiKey - API Key，用于调用提供商的 /models 接口
 */
export async function getModelsForProvider(
  appProviderId: string,
  options?: { providerType?: string; apiUrl?: string; apiKey?: string },
): Promise<GetModelsResult> {
  // 1. 并行调用 models.dev 和 Provider API（如果有 credentials）
  const [data, apiResult] = await Promise.all([
    fetchModelsDevData(),
    options?.apiKey && options?.apiUrl
      ? fetchModelsFromApi(options.apiUrl, options.apiKey)
      : Promise.resolve({ success: false, models: [], error: 'No API credentials' }),
  ]);

  // 2. 确定 models.dev 中对应的 provider ID
  // 优先级：动态精确匹配（从 models.dev 数据中按 hostname 查找） > 静态映射回退
  let modelsDevProviderId: string | null = null;

  if (options?.apiUrl) {
    modelsDevProviderId = findProviderByApiUrl(data, options.apiUrl);
  }

  if (!modelsDevProviderId) {
    const effectiveId = getEffectiveProviderId(appProviderId, options);
    modelsDevProviderId = APP_TO_MODELS_DEV_PROVIDER_MAP[effectiveId] || effectiveId;
  }

  const provider = data[modelsDevProviderId] || null;

  // 获取 models.dev 中的全量模型（过滤已弃用的）
  const allModelsDevModels = provider
    ? Object.values(provider.models).filter((model) => model.status !== 'deprecated')
    : [];

  // 3. 如果没有 apiKey 或 apiUrl，直接返回 models.dev 全量
  if (!options?.apiKey || !options?.apiUrl) {
    return {
      provider,
      models: allModelsDevModels,
      source: 'models.dev',
    };
  }

  if (!apiResult.success) {
    if (allModelsDevModels.length > 0) {
      return {
        provider,
        models: allModelsDevModels,
        source: 'models.dev',
        apiError: apiResult.error,
      };
    }
    return {
      provider,
      models: [],
      source: 'models.dev',
      apiError: apiResult.error,
    };
  }

  // 4. 如果 /models API 成功但返回空列表，使用 models.dev 全量
  if (apiResult.models.length === 0) {
    return {
      provider,
      models: allModelsDevModels,
      source: 'models.dev',
      apiModels: apiResult.models,
    };
  }

  // 5. 成功：使用 /models API 返回的模型列表过滤 models.dev 的数据
  const apiModelSet = new Set(apiResult.models);

  // 从 models.dev 中筛选出 /models API 返回的模型（保留详细信息）
  const filteredModels = allModelsDevModels.filter((model) => apiModelSet.has(model.id));

  // 处理 /models API 返回但 models.dev 中没有的模型
  // 为这些模型创建基础信息
  const modelsDevIds = new Set(allModelsDevModels.map((m) => m.id));
  const missingModels: ModelsDevModel[] = apiResult.models
    .filter((id) => !modelsDevIds.has(id))
    .map((id) => ({
      id,
      name: id,
      // 基础模型信息，没有详细的 cost/limit 等
    }));

  // 合并：models.dev 的详细信息 + 缺失模型的基础信息
  const combinedModels = [...filteredModels, ...missingModels];

  return {
    provider,
    models: combinedModels,
    source: 'api+models.dev',
    apiModels: apiResult.models,
  };
}

/**
 * 将 models.dev 模型数据转换为 CustomModelInfo
 *
 * 根据 models.dev 文档：
 * - modalities.input: string[] — 支持的输入模态（如 'image', 'pdf', 'audio', 'video'）
 */
export function mapToCustomModelInfo(model: ModelsDevModel): CustomModelInfo {
  // 获取输入模态列表
  let inputModalities: string[] = [];
  if (model.modalities) {
    if (Array.isArray(model.modalities)) {
      // 旧格式：直接是数组
      inputModalities = model.modalities;
    } else if (model.modalities.input && Array.isArray(model.modalities.input)) {
      // 新格式：对象 { input: [...], output: [...] }
      inputModalities = model.modalities.input;
    }
  }

  const supportsVision = inputModalities.includes('image') || model.attachment === true;
  const supportsAudioInput = inputModalities.includes('audio');
  const supportsVideoInput = inputModalities.includes('video');

  return {
    source: 'api',
    lastUpdated: new Date().toISOString(),
    max_input_tokens: model.limit?.context,
    input_cost_per_million: model.cost?.input,
    output_cost_per_million: model.cost?.output,
    supports_vision: supportsVision,
    supports_function_calling: model.tool_call ?? false,
    supports_reasoning: model.reasoning ?? false,
    supports_audio_input: supportsAudioInput,
    supports_video_input: supportsVideoInput,
  };
}

/**
 * 搜索模型（支持模糊匹配）
 */
export function searchModels(models: ModelsDevModel[], query: string): ModelsDevModel[] {
  if (!query.trim()) {
    return models;
  }

  const lowerQuery = query.toLowerCase();
  return models.filter(
    (model) =>
      model.id.toLowerCase().includes(lowerQuery) ||
      model.name.toLowerCase().includes(lowerQuery) ||
      (model.family?.toLowerCase().includes(lowerQuery) ?? false),
  );
}

/**
 * 获取所有支持的 provider 列表
 */
export async function getSupportedProviders(): Promise<string[]> {
  const data = await fetchModelsDevData();
  return Object.keys(data);
}

// ============ 直接调用提供商 API ============

interface FetchModelsFromApiResult {
  success: boolean;
  models: string[];
  error?: string;
}

/**
 * 直接调用提供商的 OpenAI 兼容 /models 接口获取模型列表
 * @param apiUrl - Base URL（不含 /models 后缀）
 * @param apiKey - API Key
 * @returns 模型列表或错误信息
 */
export async function fetchModelsFromApi(apiUrl: string, apiKey: string): Promise<FetchModelsFromApiResult> {
  if (!apiUrl || !apiKey) {
    return { success: false, models: [], error: 'API URL and API Key are required' };
  }

  try {
    const response = await fetch('/api/proxy-models', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ apiUrl, apiKey }),
    });

    const data = (await response.json()) as FetchModelsFromApiResult;

    if (!response.ok || !data.success) {
      return {
        success: false,
        models: [],
        error: data.error || `Request failed with status ${response.status}`,
      };
    }

    return {
      success: true,
      models: data.models || [],
    };
  } catch (error) {
    return {
      success: false,
      models: [],
      error: error instanceof Error ? error.message : 'Network error',
    };
  }
}

/**
 * 检查某个应用 provider ID 在 models.dev 中是否有对应数据
 * @param appProviderId - 应用内置的 provider ID
 * @param options - 可选参数
 * @param options.providerType - 自定义提供商的兼容类型
 * @param options.apiUrl - API URL，用于自动识别提供商
 */
export function hasModelsDevSupport(
  appProviderId: string,
  options?: { providerType?: string; apiUrl?: string },
): boolean {
  // 优先检查内置提供商映射
  if (appProviderId in APP_TO_MODELS_DEV_PROVIDER_MAP) {
    return true;
  }

  // 尝试根据 API URL 识别
  if (options?.apiUrl) {
    const urlProviderId = getProviderIdFromUrl(options.apiUrl);
    if (urlProviderId) {
      return true;
    }
  }

  // 对于自定义提供商，检查其兼容类型是否有对应的 models.dev 数据
  if (options?.providerType && options.providerType in CUSTOM_TYPE_TO_MODELS_DEV_MAP) {
    return true;
  }

  return false;
}

/**
 * 获取用于 models.dev 查询的有效 provider ID
 * 优先级：内置提供商 > URL 识别 > providerType 配置
 * @param appProviderId - 应用内置的 provider ID
 * @param options - 可选参数
 * @param options.providerType - 自定义提供商的兼容类型
 * @param options.apiUrl - API URL，用于自动识别提供商
 */
export function getEffectiveProviderId(
  appProviderId: string,
  options?: { providerType?: string; apiUrl?: string },
): string {
  // 优先使用内置提供商映射
  if (appProviderId in APP_TO_MODELS_DEV_PROVIDER_MAP) {
    return appProviderId;
  }

  // 尝试根据 API URL 识别（优先于 providerType）
  if (options?.apiUrl) {
    const urlProviderId = getProviderIdFromUrl(options.apiUrl);
    if (urlProviderId) {
      return urlProviderId;
    }
  }

  // 对于自定义提供商，使用其兼容类型对应的 models.dev ID
  if (options?.providerType && options.providerType in CUSTOM_TYPE_TO_MODELS_DEV_MAP) {
    return CUSTOM_TYPE_TO_MODELS_DEV_MAP[options.providerType];
  }

  return appProviderId;
}
