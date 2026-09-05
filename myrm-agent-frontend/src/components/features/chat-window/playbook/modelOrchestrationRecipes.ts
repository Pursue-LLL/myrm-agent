/**
 * [INPUT]
 * - @/store/config/providerTypes::SingleModelSelection (POS: 模型选择引用契约)
 * - @/store/useProviderStore::useProviderStore (POS: 模型服务状态总线)
 *
 * [OUTPUT]
 * - MODEL_ORCHESTRATION_RECIPES: 三大黄金编排预设定义
 * - resolveRecipeReadiness: 判定当前已启用模型与预设的适配就绪度
 * - applyOrchestrationRecipe: 原子增量应用编排预设
 *
 * [POS]
 * 模型编排最佳实践预设引擎。负责编排方案模型匹配规则、适配度计算与状态无缝下发。
 */

import { type SingleModelSelection } from '@/store/config/providerTypes';
import type { AgentModelSelection } from '@/services/agent';

export type RecipeTierId = 'frugal' | 'balanced' | 'consensus';

export interface EnabledModelOption {
  providerId: string;
  providerName: string;
  model: string;
}

export interface ModelOrchestrationRecipe {
  id: RecipeTierId;
  titleKey: string;
  badgeKey: string;
  accentColor: 'emerald' | 'purple' | 'amber';
  descriptionKey: string;
  brainRoleKey: string;
  handsRoleKey: string;
  costBenefitKey: string;
  caveatKey?: string;
  routingEnabled: boolean;
  autoMoaReasoning: boolean;
  brainPatterns: RegExp[];
  handsPatterns: RegExp[];
}

export interface RecipeReadiness {
  isReady: boolean;
  primaryMatch: SingleModelSelection | null;
  lightMatch: SingleModelSelection | null;
  reasoningMatch: SingleModelSelection | null;
  missingRoleKey?: string;
}

export const MODEL_ORCHESTRATION_RECIPES: ModelOrchestrationRecipe[] = [
  {
    id: 'frugal',
    titleKey: 'frugalTitle',
    badgeKey: 'frugalBadge',
    accentColor: 'emerald',
    descriptionKey: 'frugalDesc',
    brainRoleKey: 'frugalBrainRole',
    handsRoleKey: 'frugalHandsRole',
    costBenefitKey: 'frugalCostBenefit',
    routingEnabled: false,
    autoMoaReasoning: false,
    brainPatterns: [/deepseek/i, /flash/i, /mini/i, /qwen/i, /haiku/i],
    handsPatterns: [/deepseek/i, /flash/i, /mini/i, /qwen/i, /haiku/i],
  },
  {
    id: 'balanced',
    titleKey: 'balancedTitle',
    badgeKey: 'balancedBadge',
    accentColor: 'purple',
    descriptionKey: 'balancedDesc',
    brainRoleKey: 'balancedBrainRole',
    handsRoleKey: 'balancedHandsRole',
    costBenefitKey: 'balancedCostBenefit',
    routingEnabled: true,
    autoMoaReasoning: false,
    brainPatterns: [/sonnet/i, /opus/i, /r1/i, /gpt-4o(?!-mini)/i, /o1/i, /o3/i, /pro/i],
    handsPatterns: [/deepseek/i, /flash/i, /mini/i, /qwen/i, /haiku/i],
  },
  {
    id: 'consensus',
    titleKey: 'consensusTitle',
    badgeKey: 'consensusBadge',
    accentColor: 'amber',
    descriptionKey: 'consensusDesc',
    brainRoleKey: 'consensusBrainRole',
    handsRoleKey: 'consensusHandsRole',
    costBenefitKey: 'consensusCostBenefit',
    caveatKey: 'consensusCaveat',
    routingEnabled: true,
    autoMoaReasoning: true,
    brainPatterns: [/sonnet/i, /r1/i, /gpt-4o/i, /deepseek/i, /pro/i],
    handsPatterns: [/deepseek/i, /flash/i, /mini/i, /qwen/i],
  },
];

export function findBestModelMatch(
  enabledModels: EnabledModelOption[],
  patterns: RegExp[],
  fallbackExclude?: SingleModelSelection | null,
): SingleModelSelection | null {
  if (!enabledModels || enabledModels.length === 0) {
    return null;
  }

  // 1. 尝试匹配模式，避开被排除的模型
  for (const pattern of patterns) {
    const candidate = enabledModels.find(
      (m) =>
        pattern.test(m.model) &&
        (!fallbackExclude || fallbackExclude.providerId !== m.providerId || fallbackExclude.model !== m.model),
    );
    if (candidate) {
      return { providerId: candidate.providerId, model: candidate.model };
    }
  }

  // 2. 尝试无排除匹配
  for (const pattern of patterns) {
    const candidate = enabledModels.find((m) => pattern.test(m.model));
    if (candidate) {
      return { providerId: candidate.providerId, model: candidate.model };
    }
  }

  // 3. 兜底选取第一个可用模型
  const first = enabledModels[0];
  return first ? { providerId: first.providerId, model: first.model } : null;
}

export function resolveRecipeReadiness(
  recipe: ModelOrchestrationRecipe,
  enabledModels: EnabledModelOption[],
): RecipeReadiness {
  if (!enabledModels || enabledModels.length === 0) {
    return {
      isReady: false,
      primaryMatch: null,
      lightMatch: null,
      reasoningMatch: null,
      missingRoleKey: 'noModelsEnabled',
    };
  }

  if (recipe.id === 'frugal') {
    const match = findBestModelMatch(enabledModels, recipe.handsPatterns);
    return {
      isReady: Boolean(match),
      primaryMatch: match,
      lightMatch: match,
      reasoningMatch: null,
      missingRoleKey: match ? undefined : 'missingFrugalModel',
    };
  }

  if (recipe.id === 'balanced') {
    const brainMatch = findBestModelMatch(enabledModels, recipe.brainPatterns);
    const handsMatch = findBestModelMatch(enabledModels, recipe.handsPatterns, brainMatch);

    const isReady = Boolean(brainMatch && handsMatch);
    return {
      isReady,
      primaryMatch: brainMatch,
      lightMatch: handsMatch,
      reasoningMatch: brainMatch,
      missingRoleKey: !brainMatch ? 'missingBrainModel' : !handsMatch ? 'missingHandsModel' : undefined,
    };
  }

  // consensus 模式
  const reasoningMatch = findBestModelMatch(enabledModels, recipe.brainPatterns);
  const lightMatch = findBestModelMatch(enabledModels, recipe.handsPatterns, reasoningMatch);

  const isReady = Boolean(reasoningMatch && lightMatch);
  return {
    isReady,
    primaryMatch: reasoningMatch,
    lightMatch,
    reasoningMatch,
    missingRoleKey: !reasoningMatch ? 'missingBrainModel' : !lightMatch ? 'missingHandsModel' : undefined,
  };
}

export interface ProviderStoreApplyActions {
  setBaseModel: (selection: SingleModelSelection | null) => void;
  setLiteModel: (selection: SingleModelSelection | null) => void;
  setRoutingEnabled: (enabled: boolean) => void;
  setRoutingLightModel: (selection: SingleModelSelection | null) => void;
  setRoutingReasoningModel: (selection: SingleModelSelection | null) => void;
  setAutoMoaReasoning: (enabled: boolean) => void;
}

export function applyOrchestrationRecipe(
  recipe: ModelOrchestrationRecipe,
  readiness: RecipeReadiness,
  actions: ProviderStoreApplyActions,
): boolean {
  if (!readiness.isReady || !readiness.primaryMatch) {
    return false;
  }

  actions.setBaseModel(readiness.primaryMatch);

  if (readiness.lightMatch) {
    actions.setLiteModel(readiness.lightMatch);
  }

  actions.setRoutingEnabled(recipe.routingEnabled);

  if (recipe.routingEnabled) {
    if (readiness.lightMatch) {
      actions.setRoutingLightModel(readiness.lightMatch);
    }
    if (readiness.reasoningMatch) {
      actions.setRoutingReasoningModel(readiness.reasoningMatch);
    }
    actions.setAutoMoaReasoning(recipe.autoMoaReasoning);
  } else {
    actions.setAutoMoaReasoning(false);
  }

  return true;
}

/**
 * 将编排预设应用到 Agent Profile 的模型选择契约上
 */
export function applyRecipeToAgentModelSelection(
  recipe: ModelOrchestrationRecipe,
  readiness: RecipeReadiness,
  current: AgentModelSelection | null,
): AgentModelSelection | null {
  if (!readiness.isReady || !readiness.primaryMatch) {
    return null;
  }

  const base: AgentModelSelection = current
    ? { ...current }
    : {
        providerId: readiness.primaryMatch.providerId,
        model: readiness.primaryMatch.model,
      };

  // 更新主模型
  base.providerId = readiness.primaryMatch.providerId;
  base.model = readiness.primaryMatch.model;

  base.routingEnabled = recipe.routingEnabled;

  if (recipe.routingEnabled) {
    if (readiness.lightMatch) {
      base.lightProviderId = readiness.lightMatch.providerId;
      base.lightModel = readiness.lightMatch.model;
    }
    if (readiness.reasoningMatch) {
      base.reasoningProviderId = readiness.reasoningMatch.providerId;
      base.reasoningModel = readiness.reasoningMatch.model;
    }
  } else {
    // 纯轻量省流模式下，清空多余重推理槽位
    base.lightProviderId = undefined;
    base.lightModel = undefined;
    base.reasoningProviderId = undefined;
    base.reasoningModel = undefined;
  }

  return base;
}

