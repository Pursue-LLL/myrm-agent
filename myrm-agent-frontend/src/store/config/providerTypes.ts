/**
 * [INPUT]
 * ./providerCatalog::BUILT_IN_PROVIDERS, BUILT_IN_PROVIDER_INFO (POS: built-in provider catalog data)
 * ./providerRouting.generated::KNOWN_ROUTE_PREFIXES, PROVIDER_TO_ROUTE_PREFIX (POS: route segments generated from the
 * harness routing table)
 *
 * [OUTPUT]
 * ProviderConfig, ApiKeyConfig, CredentialPoolStrategy: persisted shape of one provider row
 * CUSTOM_PROVIDER_TYPES, CustomProviderType, CustomProviderTypeInfo, CUSTOM_PROVIDER_TYPE_INFO,
 * resolveCustomProviderTypeInfo: the compatibility types a custom provider can declare
 * ProviderCategory, getProviderCategory: api or local provider
 * getRoutedModelName, PROVIDER_TO_ROUTE_PREFIX: the `<route>/<model>` id the backend resolves
 * hasActiveApiKey, supportsProviderNoAuth, hasUsableProviderAuth, resolveProviderApiKeyForRequests,
 * isTrustedSplitStackHostname, isLocalOrTrustedSplitStackApiUrl, LOCAL_NO_AUTH_API_KEY_MARKER,
 * OAUTH_AUTH_API_KEY_MARKER: whether a provider can authenticate and which credential a request carries
 * SingleModelSelection, CustomModelInfo, ModelSlot, RoutingConfig, DefaultModelConfig: model-selection shapes
 * getInitialProviders, getInitialDefaultModelConfig: first-run state
 *
 * [POS]
 * Domain model of the provider settings: what a provider row holds, when it counts as usable and how a model is
 * named for the backend.
 */

import { BUILT_IN_PROVIDER_INFO, BUILT_IN_PROVIDERS } from './providerCatalog';
import {
  KNOWN_ROUTE_PREFIXES as _GENERATED_ROUTE_PREFIXES,
  PROVIDER_TO_ROUTE_PREFIX,
} from './providerRouting.generated';

export { PROVIDER_TO_ROUTE_PREFIX };

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
  routePrefix: string;
}

// 自定义提供商类型配置
export const CUSTOM_PROVIDER_TYPE_INFO: Record<CustomProviderType, CustomProviderTypeInfo> = {
  'openai-like': {
    id: 'openai-like',
    name: 'OpenAI-Like',
    defaultApiUrl: 'https://api.openai.com/v1',
    routePrefix: 'openai',
  },
  'gemini-like': {
    id: 'gemini-like',
    name: 'Gemini-Like',
    defaultApiUrl: 'https://generativelanguage.googleapis.com/v1beta',
    routePrefix: 'gemini',
  },
  'anthropic-like': {
    id: 'anthropic-like',
    name: 'Anthropic-Like',
    defaultApiUrl: 'https://api.anthropic.com',
    routePrefix: 'anthropic',
  },
};

/** Resolve custom provider compat metadata; ignores legacy/invalid providerType values. */
export function resolveCustomProviderTypeInfo(providerType?: string): CustomProviderTypeInfo | undefined {
  if (!providerType || !CUSTOM_PROVIDER_TYPES.includes(providerType as CustomProviderType)) {
    return undefined;
  }
  return CUSTOM_PROVIDER_TYPE_INFO[providerType as CustomProviderType];
}

/** Known provider route segments (longest first; generated list plus custom compat prefixes). */
const KNOWN_ROUTE_PREFIXES: readonly string[] = (() => {
  const routePrefixesFromCustom = Object.values(CUSTOM_PROVIDER_TYPE_INFO).map((t) => t.routePrefix);
  return [...new Set([..._GENERATED_ROUTE_PREFIXES, ...routePrefixesFromCustom, 'vercel_ai_gateway'])].sort(
    (a, b) => b.length - a.length,
  );
})();

// 获取带路由段的模型全名
/**
 * Resolve the route segment for a provider row.
 *
 * Built-in ids carry an explicit generated mapping. A custom provider id has no mapping, so the row's
 * providerType decides the route: legacy rows store a bare provider id there (e.g. `openai` for an
 * OpenAI-compatible gateway). Without this the caller would build `custom-id/model`, a route the backend does
 * not know, and every request would fail to resolve a provider.
 */
function resolveRoutePrefix(providerId: string, providerType?: string): string {
  const mapped = PROVIDER_TO_ROUTE_PREFIX[providerId];
  if (mapped) {
    return mapped;
  }
  if (providerType && KNOWN_ROUTE_PREFIXES.includes(providerType)) {
    return providerType;
  }
  return providerId;
}

export const getRoutedModelName = (
  providerId: string,
  modelName: string,
  // Legacy rows store a bare provider id here (e.g. "openai"), so the value is wider than the custom
  // provider types while literal autocomplete still works.
  providerType?: CustomProviderType | (string & {}),
): string => {
  const normalizedModelName = modelName.toLowerCase();
  if (providerId === 'vercel_ai_gateway') {
    if (normalizedModelName.startsWith('vercel_ai_gateway/')) {
      return modelName;
    }
    return `vercel_ai_gateway/${modelName}`;
  }

  for (const routePrefix of KNOWN_ROUTE_PREFIXES) {
    if (normalizedModelName.startsWith(`${routePrefix}/`)) {
      return modelName;
    }
  }

  // Keep the raw value: a legacy row stores a bare provider id here (e.g. "openai"), which is exactly the
  // route segment the row needs.
  const rawProviderType = providerType;
  if (providerType && !CUSTOM_PROVIDER_TYPES.includes(providerType as CustomProviderType)) {
    // 如果 providerType 不是自定义类型，则忽略它，使用 providerId
    providerType = undefined;
  }
  if (providerType && CUSTOM_PROVIDER_TYPES.includes(providerType as CustomProviderType)) {
    const typeInfo = CUSTOM_PROVIDER_TYPE_INFO[providerType as CustomProviderType];
    if (normalizedModelName.startsWith(`${typeInfo.routePrefix}/`)) {
      return modelName;
    }
    return `${typeInfo.routePrefix}/${modelName}`;
  }
  const prefix = resolveRoutePrefix(providerId, rawProviderType);
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
  /** Routing segment (may differ from id for multi-gateway OpenAI-compat vendors). */
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
  oauthConnected?: boolean;
  egressProxy?: string;
}

export const LOCAL_NO_AUTH_API_KEY_MARKER = '__myrm_local_no_auth__';
export const OAUTH_AUTH_API_KEY_MARKER = '__myrm_oauth_token__';

function isLoopbackHostname(hostname: string): boolean {
  const normalized = hostname
    .toLowerCase()
    .trim()
    .replace(/^\[|\]$/g, '');
  if (normalized === 'localhost') {
    return true;
  }
  if (normalized === '127.0.0.1') {
    return true;
  }
  if (normalized === '::1') {
    return true;
  }
  if (normalized === '0.0.0.0') {
    return true;
  }
  return false;
}

export function isTrustedSplitStackHostname(hostname: string): boolean {
  const normalized = hostname
    .toLowerCase()
    .trim()
    .replace(/^\[|\]$/g, '');
  if (normalized === 'localhost' || normalized.endsWith('.local')) {
    return true;
  }
  if (isLoopbackHostname(normalized)) {
    return true;
  }

  const ipv4Parts = normalized.split('.');
  if (ipv4Parts.length === 4) {
    const p0 = Number(ipv4Parts[0]);
    const p1 = Number(ipv4Parts[1]);
    const p2 = Number(ipv4Parts[2]);
    const p3 = Number(ipv4Parts[3]);

    if ([p0, p1, p2, p3].every((p) => Number.isInteger(p) && p >= 0 && p <= 255)) {
      // Explicitly reject link-local (169.254.0.0/16, cloud metadata)
      if (p0 === 169 && p1 === 254) {
        return false;
      }
      // Loopback
      if (p0 === 127) {
        return true;
      }
      // RFC1918 10.0.0.0/8
      if (p0 === 10) {
        return true;
      }
      // RFC1918 172.16.0.0/12
      if (p0 === 172 && p1 >= 16 && p1 <= 31) {
        return true;
      }
      // RFC1918 192.168.0.0/16
      if (p0 === 192 && p1 === 168) {
        return true;
      }
      // Tailscale CGNAT 100.64.0.0/10
      if (p0 === 100 && p1 >= 64 && p1 <= 127) {
        return true;
      }
    }
  }

  return false;
}

export const isLocalOrTrustedSplitStackApiUrl = (apiUrl?: string | null): boolean => {
  if (!apiUrl) {
    return false;
  }
  const trimmed = apiUrl.trim();
  if (!trimmed) {
    return false;
  }
  const candidate = trimmed.includes('://') ? trimmed : `http://${trimmed}`;
  try {
    const parsed = new URL(candidate);
    return isTrustedSplitStackHostname(parsed.hostname);
  } catch {
    return false;
  }
};

export const hasActiveApiKey = (provider: Pick<ProviderConfig, 'apiKeys'>): boolean => {
  return provider.apiKeys?.some((k) => k.isActive && k.key) ?? false;
};

export const supportsProviderNoAuth = (provider: Pick<ProviderConfig, 'id' | 'providerType' | 'apiUrl'>): boolean => {
  if (provider.id === 'ollama' || provider.id === 'lm_studio') {
    return true;
  }
  if (provider.providerType === 'openai-like' && isLocalOrTrustedSplitStackApiUrl(provider.apiUrl)) {
    return true;
  }
  return false;
};

export const hasUsableProviderAuth = (
  provider: Pick<ProviderConfig, 'id' | 'providerType' | 'apiUrl' | 'apiKeys'> & { oauthConnected?: boolean },
): boolean => {
  return hasActiveApiKey(provider) || supportsProviderNoAuth(provider) || Boolean(provider.oauthConnected);
};

export const resolveProviderApiKeyForRequests = (
  provider: Pick<ProviderConfig, 'id' | 'providerType' | 'apiUrl' | 'apiKeys'> & { oauthConnected?: boolean },
): string | undefined => {
  const active = provider.apiKeys.find((k) => k.isActive && k.key)?.key;
  if (active) {
    return active;
  }
  if (supportsProviderNoAuth(provider)) {
    return LOCAL_NO_AUTH_API_KEY_MARKER;
  }
  if (provider.oauthConnected) {
    return OAUTH_AUTH_API_KEY_MARKER;
  }
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
  /** Cost per million cache-read tokens (USD). */
  cache_read_cost_per_million?: number;
  /** Cost per million cache-write tokens (USD). */
  cache_write_cost_per_million?: number;
  supports_vision?: boolean;
  supports_function_calling?: boolean;
  supports_reasoning?: boolean;
  /** Responses API wire (read-only metadata from import/heuristics). */
  supports_audio_input?: boolean;
  supports_video_input?: boolean;
  temperature?: number;
  extraParams?: Record<string, unknown>;
}

// 模型槽位：主模型 + 可选备用模型 / 有序备用链
export interface ModelSlot {
  primary: SingleModelSelection | null;
  fallback: SingleModelSelection | null;
  fallbacks?: SingleModelSelection[];
  temperature?: number;
  modelKwargs?: Record<string, unknown>;
}

// 智能路由配置：根据任务复杂度自动选择模型层级
export interface RoutingConfig {
  enabled: boolean;
  lightModel: ModelSlot;
  reasoningModel: ModelSlot;
  autoMoaReasoning?: boolean;
  autoMoaPresetId?: 'default' | 'review' | 'fast';
}

// 默认模型配置
export interface DefaultModelConfig {
  baseModel: ModelSlot;
  liteModel: ModelSlot;
  fastModeModel: ModelSlot | null;
  routingConfig: RoutingConfig | null;
  visionFallbackModel?: ModelSlot | null;
  videoFallbackModel?: ModelSlot | null;
  codeModel?: ModelSlot | null;
  longDocModel?: ModelSlot | null;
  backgroundEvolutionModel?: ModelSlot | null;
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
      routingProfile: PROVIDER_TO_ROUTE_PREFIX[id] ?? id,
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
  videoFallbackModel: null,
  codeModel: null,
  longDocModel: null,
  backgroundEvolutionModel: null,
});
