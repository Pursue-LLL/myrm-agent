/**
 * [INPUT] store/config/providerTypes::BuiltInProviderId (POS: 内置 LLM Provider ID 枚举)
 * [OUTPUT] BUILT_IN_PROVIDER_ICON_LOADERS: 内置 Provider 品牌 SVG 按需加载映射
 * [POS] model-service 层 LobeHub static SVG 加载器；每个 Provider 独立 dynamic import chunk，零 peer 依赖。
 */

import type { BuiltInProviderId } from '@/store/config/providerTypes';

export type ProviderBrandIconModule = { default: string };

export type ProviderBrandIconLoader = () => Promise<ProviderBrandIconModule>;

/** LobeHub static SVG slug (without `.svg`) — SSOT for filesystem existence tests. */
export const BUILT_IN_PROVIDER_SVG_SLUGS: Record<BuiltInProviderId, string> = {
  openai: 'openai',
  anthropic: 'anthropic',
  gemini: 'gemini-color',
  deepseek: 'deepseek-color',
  openrouter: 'openrouter-color',
  zai: 'zai',
  xai: 'xai',
  ollama: 'ollama',
  moonshot: 'moonshot',
  lm_studio: 'lmstudio',
  groq: 'groq',
  dashscope: 'qwen-color',
  minimax: 'minimax-color',
  mistral: 'mistral-color',
  together_ai: 'together-color',
  siliconflow: 'siliconcloud-color',
  volcengine: 'doubao-color',
  fireworks_ai: 'fireworks-color',
  azure: 'azure-color',
  spark: 'spark-color',
  perplexity: 'perplexity-color',
  jina_ai: 'jina',
  bedrock: 'bedrock-color',
  xiaomi_mimo: 'xiaomimimo',
  nvidia: 'nvidia-color',
  ai302: 'ai302-color',
  opencode_go: 'opencode',
};

/**
 * Explicit per-provider dynamic imports — required for webpack/turbopack code splitting.
 * Do not replace with template literals.
 */
export const BUILT_IN_PROVIDER_ICON_LOADERS: Record<BuiltInProviderId, ProviderBrandIconLoader> = {
  openai: () => import('@lobehub/icons-static-svg/icons/openai.svg'),
  anthropic: () => import('@lobehub/icons-static-svg/icons/anthropic.svg'),
  gemini: () => import('@lobehub/icons-static-svg/icons/gemini-color.svg'),
  deepseek: () => import('@lobehub/icons-static-svg/icons/deepseek-color.svg'),
  openrouter: () => import('@lobehub/icons-static-svg/icons/openrouter-color.svg'),
  zai: () => import('@lobehub/icons-static-svg/icons/zai.svg'),
  xai: () => import('@lobehub/icons-static-svg/icons/xai.svg'),
  ollama: () => import('@lobehub/icons-static-svg/icons/ollama.svg'),
  moonshot: () => import('@lobehub/icons-static-svg/icons/moonshot.svg'),
  lm_studio: () => import('@lobehub/icons-static-svg/icons/lmstudio.svg'),
  groq: () => import('@lobehub/icons-static-svg/icons/groq.svg'),
  dashscope: () => import('@lobehub/icons-static-svg/icons/qwen-color.svg'),
  minimax: () => import('@lobehub/icons-static-svg/icons/minimax-color.svg'),
  mistral: () => import('@lobehub/icons-static-svg/icons/mistral-color.svg'),
  together_ai: () => import('@lobehub/icons-static-svg/icons/together-color.svg'),
  siliconflow: () => import('@lobehub/icons-static-svg/icons/siliconcloud-color.svg'),
  volcengine: () => import('@lobehub/icons-static-svg/icons/doubao-color.svg'),
  fireworks_ai: () => import('@lobehub/icons-static-svg/icons/fireworks-color.svg'),
  azure: () => import('@lobehub/icons-static-svg/icons/azure-color.svg'),
  spark: () => import('@lobehub/icons-static-svg/icons/spark-color.svg'),
  perplexity: () => import('@lobehub/icons-static-svg/icons/perplexity-color.svg'),
  jina_ai: () => import('@lobehub/icons-static-svg/icons/jina.svg'),
  bedrock: () => import('@lobehub/icons-static-svg/icons/bedrock-color.svg'),
  xiaomi_mimo: () => import('@lobehub/icons-static-svg/icons/xiaomimimo.svg'),
  nvidia: () => import('@lobehub/icons-static-svg/icons/nvidia-color.svg'),
  ai302: () => import('@lobehub/icons-static-svg/icons/ai302-color.svg'),
  opencode_go: () => import('@lobehub/icons-static-svg/icons/opencode.svg'),
};

const iconUrlCache = new Map<BuiltInProviderId, string>();
const iconLoadPromises = new Map<BuiltInProviderId, Promise<string | null>>();

export function getCachedProviderBrandIconUrl(providerId: BuiltInProviderId): string | undefined {
  return iconUrlCache.get(providerId);
}

export async function loadProviderBrandIconUrl(providerId: BuiltInProviderId): Promise<string | null> {
  const cached = iconUrlCache.get(providerId);
  if (cached) {
    return cached;
  }

  const inFlight = iconLoadPromises.get(providerId);
  if (inFlight) {
    return inFlight;
  }

  const promise = BUILT_IN_PROVIDER_ICON_LOADERS[providerId]()
    .then((mod) => {
      const url = mod.default;
      iconUrlCache.set(providerId, url);
      return url;
    })
    .catch(() => null)
    .finally(() => {
      iconLoadPromises.delete(providerId);
    });

  iconLoadPromises.set(providerId, promise);
  return promise;
}

/** Test-only: reset module-level caches between cases. */
export function resetProviderBrandIconCacheForTests(): void {
  iconUrlCache.clear();
  iconLoadPromises.clear();
}
