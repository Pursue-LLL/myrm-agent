/**
 * [INPUT] @/store/config/providerTypes::getRoutedModelName, isLocalOrTrustedSplitStackApiUrl (POS: 路由名与本地 / 受信任私网端点判定), @/services/llm-config (POS: 模型能力与压缩预检 DTO)
 * [OUTPUT] collectLocalCapabilities / mergeFetchedCapabilities / applyLocalOwnedFallbacks: 模型能力与成本映射; groupModelsByProvider: 搜索过滤与 Provider 分组（含 $0 / free / local 查询）; buildPreflightPairs / buildPreflightSignature / mapPreflightResults: 压缩预检请求与结果映射
 * [POS] ModelPickerPopover 的纯数据逻辑与共享类型，无 React 依赖。
 */

import type { ModelCapabilities, ModelSwitchPreflightResult } from '@/services/llm-config';
import {
  getRoutedModelName,
  isLocalOrTrustedSplitStackApiUrl,
  type CustomModelInfo,
  type ProviderConfig,
} from '@/store/config/providerTypes';

export interface PickerModelSelection {
  providerId: string;
  model: string;
}

export type SlotMode = 'primary' | 'fallback' | 'safety';

export interface MoaPresetOption {
  id: string;
  label: string;
  refCount: number;
}

/** One entry of `useProviderStore().getEnabledModels()`. */
export interface EnabledModel {
  providerId: string;
  providerName: string;
  model: string;
}

/** USD per million tokens; `isLocalOwned` marks self-hosted endpoints whose marginal cost is zero. */
export interface ModelCost {
  input: number;
  output: number;
  isLocalOwned?: boolean;
}

export interface ProviderModels {
  provider: ProviderConfig;
  models: string[];
}

export interface PreflightPair {
  providerId: string;
  model: string;
  liteName: string;
  maxInput: number | null;
}

export interface PreflightRequestContext {
  chatId: string | null | undefined;
  estimatedTokens: number;
  compressStartRatio: number | null | undefined;
  turnCount: number | null | undefined;
}

/** Capabilities and costs known from custom model info, plus the route names that still need a server lookup. */
export function collectLocalCapabilities(
  enabledModels: EnabledModel[],
  providers: ProviderConfig[],
  customModelInfo: Record<string, CustomModelInfo>,
) {
  const mapped: Record<string, ModelCapabilities> = {};
  const costs: Record<string, ModelCost> = {};
  const toFetch: string[] = [];
  const nameMap: Record<string, string> = {};

  for (const em of enabledModels) {
    const localKey = `${em.providerId}/${em.model}`;
    const local = customModelInfo[localKey];
    if (local) {
      mapped[em.model] = {
        supports_vision: local.supports_vision || false,
        supports_function_calling: local.supports_function_calling || false,
        supports_reasoning: local.supports_reasoning || false,
        supports_audio_input: local.supports_audio_input || false,
        supports_video_input: local.supports_video_input || false,
        supports_web_search: false,
        supports_prompt_caching: false,
        input_cost_per_token: local.input_cost_per_million || null,
        output_cost_per_token: local.output_cost_per_million || null,
        max_input_tokens: local.max_input_tokens || null,
        max_output_tokens: null,
      };
      if (typeof local.input_cost_per_million === 'number' && typeof local.output_cost_per_million === 'number') {
        costs[em.model] = { input: local.input_cost_per_million, output: local.output_cost_per_million };
      }
    } else {
      const prov = providers.find((p) => p.id === em.providerId);
      const liteName = getRoutedModelName(em.providerId, em.model, prov?.providerType);
      toFetch.push(liteName);
      nameMap[liteName] = em.model;
    }
  }

  return { mapped, costs, toFetch, nameMap };
}

/** Self-hosted endpoints (ollama, LM Studio, trusted split-stack URLs) without explicit pricing cost nothing at the margin. */
export function applyLocalOwnedFallbacks(
  targetCosts: Record<string, ModelCost>,
  enabledModels: EnabledModel[],
  providers: ProviderConfig[],
): void {
  for (const em of enabledModels) {
    if (!targetCosts[em.model]) {
      const prov = providers.find((p) => p.id === em.providerId);
      const isLocal =
        prov?.id === 'ollama' ||
        prov?.id === 'lm_studio' ||
        isLocalOrTrustedSplitStackApiUrl(prov?.apiUrl || (prov as { customApiUrl?: string })?.customApiUrl);
      if (isLocal) {
        targetCosts[em.model] = { input: 0, output: 0, isLocalOwned: true };
      }
    }
  }
}

/** Merges server-fetched capabilities (keyed by route name) into the per-model maps. */
export function mergeFetchedCapabilities(
  caps: Record<string, ModelCapabilities>,
  toFetch: string[],
  nameMap: Record<string, string>,
  mapped: Record<string, ModelCapabilities>,
  costs: Record<string, ModelCost>,
): void {
  for (const ln of toFetch) {
    if (caps[ln]) {
      const modelName = nameMap[ln];
      mapped[modelName] = caps[ln];
      const c = caps[ln];
      if (typeof c.input_cost_per_token === 'number' && typeof c.output_cost_per_token === 'number') {
        costs[modelName] = {
          input: c.input_cost_per_token * 1_000_000,
          output: c.output_cost_per_token * 1_000_000,
        };
      }
    }
  }
}

export function groupModelsByProvider(
  enabledModels: EnabledModel[],
  providers: ProviderConfig[],
  search: string,
  costPerMillion: Record<string, ModelCost>,
): ProviderModels[] {
  const q = search.toLowerCase().trim();
  const result: ProviderModels[] = [];
  const map: Record<string, ProviderModels> = {};

  const isCostZeroQuery = q === '$0' || q === '0' || q === 'free' || q === 'local' || q === '本地' || q === '免费';

  for (const em of enabledModels) {
    const cost = costPerMillion[em.model];
    const matchCostZero = isCostZeroQuery && cost?.isLocalOwned;
    const matchText =
      !q || em.model.toLowerCase().includes(q) || em.providerName.toLowerCase().includes(q) || matchCostZero;

    if (!matchText) {
      continue;
    }
    if (!map[em.providerId]) {
      const prov = providers.find((p) => p.id === em.providerId);
      if (!prov) {
        continue;
      }
      map[em.providerId] = { provider: prov, models: [] };
      result.push(map[em.providerId]);
    }
    map[em.providerId].models.push(em.model);
  }
  return result;
}

export function buildPreflightPairs(
  enabledModels: EnabledModel[],
  providers: ProviderConfig[],
  capabilities: Record<string, ModelCapabilities>,
): PreflightPair[] {
  const pairs: PreflightPair[] = [];
  for (const em of enabledModels) {
    const prov = providers.find((p) => p.id === em.providerId);
    if (!prov) {
      continue;
    }
    const caps = capabilities[em.model];
    if (!caps) {
      continue;
    }
    pairs.push({
      providerId: em.providerId,
      model: em.model,
      liteName: getRoutedModelName(em.providerId, em.model, prov.providerType),
      maxInput: caps.max_input_tokens ?? null,
    });
  }
  return pairs;
}

/** Any change of the session context or the candidate list produces a new signature and therefore a new preflight request. */
export function buildPreflightSignature(context: PreflightRequestContext, pairs: PreflightPair[]): string {
  const { chatId, estimatedTokens, compressStartRatio, turnCount } = context;
  return `${chatId ?? ''}:${estimatedTokens}:${compressStartRatio ?? ''}:${turnCount ?? ''}:${pairs
    .map((p) => `${p.liteName}:${p.maxInput}`)
    .join('|')}`;
}

/** Re-keys server results (by route name) to `providerId/model`. */
export function mapPreflightResults(
  pairs: PreflightPair[],
  results: Record<string, ModelSwitchPreflightResult>,
): Record<string, ModelSwitchPreflightResult> {
  const mapped: Record<string, ModelSwitchPreflightResult> = {};
  for (const p of pairs) {
    const result = results[p.liteName];
    if (result) {
      mapped[`${p.providerId}/${p.model}`] = result;
    }
  }
  return mapped;
}
