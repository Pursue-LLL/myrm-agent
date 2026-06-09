import { ApiError, apiRequest } from '@/lib/api';
import { parseMcpFindingsFromApiErrorDetails } from '@/lib/utils/mcpScanFindingText';
import type {
  MCPScanBatchResult,
  MCPScanResult,
  MCPServiceConfig,
  SearchServiceConfig,
  ValidationResult,
} from '@/store/config/types';

export type { MCPScanBatchResult, MCPScanFinding, MCPScanResult } from '@/store/config/types';

// 模型配置接口（用于验证 API）
export interface ModelConfig {
  model: string;
  api_key: string;
  base_url: string | null;
  model_kwargs: Record<string, unknown>;
}

// 模型能力信息接口
export interface ModelCapabilities {
  supports_vision: boolean;
  supports_function_calling: boolean;
  supports_reasoning: boolean;
  supports_audio_input: boolean;
  supports_video_input: boolean;
  supports_web_search: boolean;
  supports_prompt_caching: boolean;
  input_cost_per_token: number | null;
  output_cost_per_token: number | null;
  max_tokens: number | null;
  max_input_tokens: number | null;
  max_output_tokens: number | null;
}

// 候选模型信息
export interface ModelCandidate {
  provider: string;
  model_key: string;
  capabilities: ModelCapabilities;
}

// 模型信息响应
export interface ModelInfoResponse {
  found: boolean;
  capabilities: ModelCapabilities | null;
  candidates: ModelCandidate[] | null;
}

// 重新导出类型，便于其他模块使用
export type { ValidationResult, SearchServiceConfig, MCPServiceConfig };

// LiteLLM 提供商模型映射（硬编码，作为后备方案）
const PROVIDER_MODELS: Record<string, string[]> = {
  openai: ['gpt-4o', 'gpt-4o-mini', 'gpt-4-turbo', 'gpt-4', 'gpt-3.5-turbo', 'o1', 'o1-mini', 'o1-preview', 'o3-mini'],
  anthropic: [
    'claude-3-5-sonnet-20241022',
    'claude-3-5-haiku-20241022',
    'claude-3-opus-20240229',
    'claude-3-sonnet-20240229',
    'claude-3-haiku-20240307',
  ],
  gemini: ['gemini-2.0-flash-exp', 'gemini-1.5-pro', 'gemini-1.5-flash', 'gemini-1.0-pro'],
  deepseek: ['deepseek-chat', 'deepseek-reasoner'],
  openrouter: [
    'openai/gpt-4o',
    'anthropic/claude-3.5-sonnet',
    'google/gemini-pro',
    'meta-llama/llama-3.1-405b-instruct',
  ],
};

/**
 * 获取提供商的可用模型列表
 * 尝试从 LiteLLM API 获取，失败则使用硬编码列表
 */
export const fetchProviderModels = async (providerId: string): Promise<string[]> => {
  try {
    // 尝试从后端获取模型列表
    const response = await apiRequest<{ models: string[] }>(`/llm/models/${providerId}`, {
      method: 'GET',
    });
    if (response.models && response.models.length > 0) {
      return response.models;
    }
  } catch {
    // API 失败，使用硬编码列表
  }

  return PROVIDER_MODELS[providerId] || [];
};

/**
 * 验证 LLM 配置（提供商级别）
 */
export const validateLLM = async (config: ModelConfig): Promise<ValidationResult> => {
  const startTime = performance.now();

  try {
    await apiRequest('/llm/verify', {
      method: 'POST',
      body: JSON.stringify(config),
    });

    const latency = Math.round(performance.now() - startTime);
    return { success: true, latency };
  } catch (error) {
    const latency = Math.round(performance.now() - startTime);
    const errorMessage = error instanceof Error ? error.message : 'Network request failed';
    return { success: false, message: errorMessage, latency };
  }
};

export interface ReachabilityResult {
  reachable: boolean;
  latency_ms: number | null;
  error: string | null;
  cached: boolean;
}

type ReachabilityApiResponse = Partial<ReachabilityResult> & {
  data?: ReachabilityResult;
};

/**
 * Lightweight reachability check using 1-token probe.
 * Faster and cheaper than validateLLM — ideal for local model (Ollama) setup.
 */
export const checkModelReachability = async (config: ModelConfig): Promise<ReachabilityResult> => {
  try {
    const res = await apiRequest<ReachabilityApiResponse>('/llm/check-reachability', {
      method: 'POST',
      body: JSON.stringify(config),
    });
    if (res.data) return res.data;
    return {
      reachable: res.reachable ?? false,
      latency_ms: res.latency_ms ?? null,
      error: res.error ?? null,
      cached: res.cached ?? false,
    };
  } catch {
    return { reachable: false, latency_ms: null, error: 'Network request failed', cached: false };
  }
};


const softSearchServiceValidationFailurePatterns =
  /quota exceeded|apiconnectionerror|rate limit|service unavailable|temporarily unavailable/i;

export const isSoftSearchServiceValidationFailure = (
  result: Pick<ValidationResult, 'message' | 'retriable'>,
): boolean => {
  return result.retriable === true || softSearchServiceValidationFailurePatterns.test(result.message ?? '');
};

/**
 * 验证搜索服务配置
 */
export const validateSearchServiceConfig = async (config: SearchServiceConfig): Promise<ValidationResult> => {
  const startTime = performance.now();

  try {
    await apiRequest('/search/verify', {
      method: 'POST',
      body: JSON.stringify(config),
    });

    const latency = Math.round(performance.now() - startTime);
    return { success: true, latency };
  } catch (error) {
    const latency = Math.round(performance.now() - startTime);
    if (error instanceof ApiError) {
      return {
        success: false,
        message: error.message,
        latency,
        retriable: error.retriable,
        businessCode: error.businessCode,
      };
    }
    const errorMessage = error instanceof Error ? error.message : 'Network request failed';
    return { success: false, message: errorMessage, latency };
  }
};

export interface MCPToolDetail {
  name: string;
  description: string;
  readOnlyHint: boolean;
  destructiveHint: boolean;
  idempotentHint: boolean;
  openWorldHint: boolean;
}

interface MCPVerifyData {
  tools_count: number;
  service_name: string;
  instructions: string | null;
  tools: MCPToolDetail[];
  config_scan?: MCPScanResult;
  runtime_scan?: MCPScanResult;
}

/**
 * Static pre-flight scan for MCP configuration (no network connection).
 */
export const scanMCPConfig = async (config: MCPServiceConfig): Promise<MCPScanResult> => {
  return apiRequest<MCPScanResult>('/mcp/scan', {
    method: 'POST',
    body: JSON.stringify(config),
  });
};

export const scanMCPConfigBatch = async (configs: MCPServiceConfig[]): Promise<MCPScanBatchResult> => {
  return apiRequest<MCPScanBatchResult>('/mcp/scan-batch', {
    method: 'POST',
    body: JSON.stringify({ configs }),
  });
};

/**
 * 验证MCP服务配置
 */
export const validateMCPConfig = async (
  config: MCPServiceConfig,
  acknowledgedHighRisks = false,
): Promise<ValidationResult> => {
  const startTime = performance.now();

  try {
    const query = acknowledgedHighRisks ? '?acknowledgedHighRisks=true' : '';
    const data = await apiRequest<MCPVerifyData>(`/mcp/verify${query}`, {
      method: 'POST',
      body: JSON.stringify(config),
    });

    const latency = Math.round(performance.now() - startTime);
    return {
      success: true,
      latency,
      instructions: data.instructions ?? undefined,
    };
  } catch (error) {
    const latency = Math.round(performance.now() - startTime);
    if (error instanceof ApiError) {
      return {
        success: false,
        message: error.message,
        latency,
        scanFindings: parseMcpFindingsFromApiErrorDetails(error.details),
        retriable: error.retriable,
        businessCode: error.businessCode,
      };
    }
    const errorMessage = error instanceof Error ? error.message : 'Network request failed';
    return { success: false, message: errorMessage, latency };
  }
};

export interface FetchMCPToolsResult {
  tools: MCPToolDetail[];
  error: boolean;
}

/**
 * Fetch tool list for a given MCP server config (reuses verify endpoint).
 */
export const fetchMCPTools = async (config: MCPServiceConfig): Promise<FetchMCPToolsResult> => {
  try {
    const data = await apiRequest<MCPVerifyData>('/mcp/verify', {
      method: 'POST',
      body: JSON.stringify(config),
    });
    return { tools: data.tools ?? [], error: false };
  } catch {
    return { tools: [], error: true };
  }
};

/**
 * MCP 配置选项响应
 */
export interface MCPOptionsResponse {
  allowStdio: boolean;
  allowSse: boolean;
  allowedTypes: string[];
}

/**
 * 获取 MCP 配置选项
 * 返回当前部署环境下允许的 MCP 传输类型
 */
export const getMCPOptions = async (): Promise<MCPOptionsResponse> => {
  try {
    const response = await apiRequest<{ data: MCPOptionsResponse }>('/mcp/options', {
      method: 'GET',
    });
    return response.data;
  } catch (error) {
    console.error('Failed to fetch MCP options:', error);
    // 默认允许所有类型
    return {
      allowStdio: true,
      allowSse: true,
      allowedTypes: ['sse', 'stdio', 'streamable_http'],
    };
  }
};

// Speed test result for a single model
export interface SpeedTestResult {
  model: string;
  ttft_ms: number | null;
  throughput_tps: number | null;
  total_ms: number | null;
  total_tokens: number | null;
  status: 'ok' | 'error';
  error: string | null;
}

/**
 * Run speed test for multiple model configurations.
 * Sequentially tests TTFT and throughput for each model.
 */
export const runSpeedTest = async (models: ModelConfig[]): Promise<SpeedTestResult[]> => {
  try {
    const response = await apiRequest<{ data: SpeedTestResult[] }>('/llm/speed-test', {
      method: 'POST',
      body: JSON.stringify({ models }),
    });
    return response.data ?? (response as unknown as SpeedTestResult[]);
  } catch {
    return models.map((m) => ({
      model: m.model,
      ttft_ms: null,
      throughput_tps: null,
      total_ms: null,
      total_tokens: null,
      status: 'error' as const,
      error: 'Network request failed',
    }));
  }
};

// 模型能力信息缓存
const modelCapabilitiesCache = new Map<string, ModelCapabilities>();

// 默认能力信息
const defaultCapabilities: ModelCapabilities = {
  supports_vision: false,
  supports_function_calling: false,
  supports_reasoning: false,
  supports_audio_input: false,
  supports_video_input: false,
  supports_web_search: false,
  supports_prompt_caching: false,
  input_cost_per_token: null,
  output_cost_per_token: null,
  max_tokens: null,
  max_input_tokens: null,
  max_output_tokens: null,
};

/**
 * 获取单个模型的能力信息（新版本，支持候选模型）
 *
 * @returns ModelInfoResponse - 包含 found 标志和 capabilities 或 candidates
 */
export const fetchModelInfo = async (model: string): Promise<ModelInfoResponse> => {
  // 检查缓存
  const cached = modelCapabilitiesCache.get(model);
  if (cached) {
    return { found: true, capabilities: cached, candidates: null };
  }

  try {
    const response = await apiRequest<ModelInfoResponse>('/llm/model-info', {
      method: 'POST',
      body: JSON.stringify({ model }),
    });

    // 如果精确匹配找到，缓存结果
    if (response.found && response.capabilities) {
      modelCapabilitiesCache.set(model, response.capabilities);
    }

    return response;
  } catch {
    // 返回未找到状态
    return { found: false, capabilities: null, candidates: [] };
  }
};

/**
 * 获取单个模型的能力信息（兼容旧版本）
 * @deprecated 请使用 fetchModelInfo 获取完整响应
 */
export const fetchModelCapabilities = async (model: string): Promise<ModelCapabilities> => {
  const response = await fetchModelInfo(model);
  if (response.found && response.capabilities) {
    return response.capabilities;
  }
  return defaultCapabilities;
};

/**
 * 批量获取模型的能力信息
 */
export const fetchModelCapabilitiesBatch = async (models: string[]): Promise<Record<string, ModelCapabilities>> => {
  // 过滤出未缓存的模型
  const uncachedModels = models.filter((m) => !modelCapabilitiesCache.has(m));

  // 如果所有模型都已缓存，直接返回
  if (uncachedModels.length === 0) {
    const result: Record<string, ModelCapabilities> = {};
    for (const model of models) {
      result[model] = modelCapabilitiesCache.get(model)!;
    }
    return result;
  }

  try {
    const response = await apiRequest<Record<string, ModelCapabilities>>('/llm/model-info/batch', {
      method: 'POST',
      body: JSON.stringify({ models: uncachedModels }),
    });

    // 缓存结果
    for (const [model, capabilities] of Object.entries(response)) {
      modelCapabilitiesCache.set(model, capabilities);
    }
  } catch {
    // 静默失败，使用默认值
  }

  // 构建返回结果
  const result: Record<string, ModelCapabilities> = {};

  for (const model of models) {
    result[model] = modelCapabilitiesCache.get(model) || defaultCapabilities;
  }
  return result;
};

// ============================================================================
// MCP OAuth API
// ============================================================================

export interface MCPOAuthStartResponse {
  authorization_url: string;
  state: string;
}

export interface MCPOAuthCallbackResponse {
  server_name: string;
  connected: boolean;
  scope?: string;
}

export type MCPOAuthStatusMap = Record<string, { connected: boolean; expired: boolean; scope: string | null }>;

export const startMCPOAuth = async (params: {
  server_name: string;
  authorization_endpoint: string;
  token_endpoint: string;
  client_id: string;
  client_secret?: string;
  scope?: string;
  redirect_uri: string;
}): Promise<MCPOAuthStartResponse> => {
  return apiRequest<MCPOAuthStartResponse>('/mcp/oauth/start', {
    method: 'POST',
    body: JSON.stringify(params),
  });
};

export const handleMCPOAuthCallback = async (params: {
  server_name: string;
  code: string;
  state: string;
  redirect_uri: string;
}): Promise<MCPOAuthCallbackResponse> => {
  return apiRequest<MCPOAuthCallbackResponse>('/mcp/oauth/callback', {
    method: 'POST',
    body: JSON.stringify(params),
  });
};

export const getMCPOAuthStatus = async (): Promise<MCPOAuthStatusMap> => {
  return apiRequest<MCPOAuthStatusMap>('/mcp/oauth/status', {
    method: 'GET',
  });
};

export const disconnectMCPOAuth = async (serverName: string): Promise<void> => {
  await apiRequest(`/mcp/oauth/${encodeURIComponent(serverName)}`, {
    method: 'DELETE',
  });
};

// ---------------------------------------------------------------------------
// MCP Registry
// ---------------------------------------------------------------------------

export interface MCPRegistryServer {
  qualifiedName: string;
  displayName: string;
  description: string;
  iconUrl: string | null;
  homepage: string | null;
  useCount: number;
}

export interface MCPRegistrySearchResult {
  servers: MCPRegistryServer[];
  page: number;
  pageSize: number;
  totalPages: number;
}

export interface MCPRegistryEnvVar {
  name: string;
  description: string;
  required: boolean;
}

export interface MCPRegistryServerDetail {
  qualifiedName: string;
  displayName: string;
  description: string;
  iconUrl: string | null;
  homepage: string | null;
  useCount: number;
  transportType: string;
  envVars: MCPRegistryEnvVar[];
}

export const searchMCPRegistry = async (
  query: string = '',
  page: number = 1,
  pageSize: number = 20,
): Promise<MCPRegistrySearchResult> => {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (query) params.set('q', query);
  return apiRequest<MCPRegistrySearchResult>(`/mcp/registry/search?${params}`, { method: 'GET' });
};

export const getMCPRegistryDetail = async (qualifiedName: string): Promise<MCPRegistryServerDetail> => {
  return apiRequest<MCPRegistryServerDetail>(`/mcp/registry/detail/${encodeURIComponent(qualifiedName)}`, {
    method: 'GET',
  });
};
