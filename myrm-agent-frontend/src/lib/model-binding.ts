/**
 * 模型绑定解析模块
 *
 * 根据当前 actionMode 和智能体配置，解析应使用的活动模型。
 * 优先级链：模式/智能体绑定 > 全局默认
 */

import type { ActionMode, AgentConfig } from '@/store/chat/types';
import type { DefaultModelConfig, SingleModelSelection, ProviderConfig } from '@/store/config/providerTypes';
import { hasUsableProviderAuth } from '@/store/config/providerTypes';

export interface ResolvedModelConfig {
  selection: SingleModelSelection | null;
  temperature: number;
  modelKwargs: Record<string, unknown>;
}

/**
 * 解析当前活动的模型选择
 *
 * 优先级：
 * 1. fast 模式 → fastModeModel（如果已绑定）
 * 2. agent 模式 → agentConfig.modelSelection（如果已绑定）
 * 3. 回退 → baseModel（全局默认）
 */
export function resolveActiveModelSelection(
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
  defaultModelConfig: DefaultModelConfig,
  providers: ProviderConfig[],
): SingleModelSelection | null {
  if (actionMode === 'fast') {
    const fastPrimary = defaultModelConfig.fastModeModel?.primary;
    if (fastPrimary && isModelAvailable(fastPrimary, providers)) {
      return fastPrimary;
    }
    return defaultModelConfig.baseModel.primary;
  }

  if (actionMode === 'agent' && agentConfig?.modelSelection) {
    if (isModelAvailable(agentConfig.modelSelection, providers)) {
      return agentConfig.modelSelection;
    }
    return defaultModelConfig.baseModel.primary;
  }

  return defaultModelConfig.baseModel.primary;
}

/**
 * 解析当前活动的完整模型配置（含 temperature / modelKwargs）
 */
export function resolveActiveModelConfig(
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
  defaultModelConfig: DefaultModelConfig,
  providers: ProviderConfig[],
): ResolvedModelConfig {
  if (actionMode === 'fast') {
    const fast = defaultModelConfig.fastModeModel;
    if (fast?.primary && isModelAvailable(fast.primary, providers)) {
      return {
        selection: fast.primary,
        temperature: fast.temperature ?? 0.7,
        modelKwargs: fast.modelKwargs ?? {},
      };
    }
  }

  if (actionMode === 'agent' && agentConfig?.modelSelection) {
    if (isModelAvailable(agentConfig.modelSelection, providers)) {
      return {
        selection: agentConfig.modelSelection,
        temperature: defaultModelConfig.baseModel.temperature ?? 0.7,
        modelKwargs: defaultModelConfig.baseModel.modelKwargs ?? {},
      };
    }
  }

  return {
    selection: defaultModelConfig.baseModel.primary,
    temperature: defaultModelConfig.baseModel.temperature ?? 0.7,
    modelKwargs: defaultModelConfig.baseModel.modelKwargs ?? {},
  };
}

/**
 * 解析当前活动的备用模型选择
 *
 * 优先级：
 * 1. agent 模式 → agentConfig.fallbackModelSelection（如果已绑定）
 * 2. 回退 → baseModel.fallback（全局默认备用模型）
 */
export function resolveActiveFallbackSelection(
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
  defaultModelConfig: DefaultModelConfig,
  providers: ProviderConfig[],
): SingleModelSelection | null {
  if (actionMode === 'agent' && agentConfig?.fallbackModelSelection) {
    if (isModelAvailable(agentConfig.fallbackModelSelection, providers)) {
      return agentConfig.fallbackModelSelection;
    }
  }

  const fallback = defaultModelConfig.baseModel.fallback;
  if (fallback && isModelAvailable(fallback, providers)) {
    return fallback;
  }
  return null;
}

/**
 * 判断当前是否处于智能路由 (Auto Smart Routing) 模式
 */
export function isSmartRoutingActive(
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
  defaultModelConfig: DefaultModelConfig,
): boolean {
  if (actionMode === 'fast') {
    return false;
  }
  const isRoutingConfigured =
    agentConfig?.routingConfig?.enabled !== undefined
      ? Boolean(agentConfig.routingConfig.enabled)
      : Boolean(defaultModelConfig?.routingConfig?.enabled);

  if (!isRoutingConfigured) {
    return false;
  }
  // 显式选择具体模型时覆盖智能路由
  if (actionMode === 'agent' && agentConfig?.modelSelection) {
    return false;
  }
  return true;
}

/**
 * 判断系统是否已配置并支持智能路由
 */
export function isSmartRoutingConfigured(
  agentConfig: AgentConfig | null,
  defaultModelConfig: DefaultModelConfig,
): boolean {
  if (agentConfig?.routingConfig?.enabled !== undefined) {
    return Boolean(agentConfig.routingConfig.enabled);
  }
  return Boolean(defaultModelConfig?.routingConfig?.enabled);
}

/**
 * Model picker trigger display: primary model name plus optional session MoA preset chip and smart routing flag.
 */
export interface ModelPickerTriggerDisplay {
  modelName: string | null;
  moaPresetId: string | null;
  isSmartRouting: boolean;
}

export function resolveModelPickerTriggerDisplay(
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
  defaultModelConfig: DefaultModelConfig,
  providers: ProviderConfig[],
  activeMoaPresetId: string | null,
): ModelPickerTriggerDisplay {
  const isSmart = isSmartRoutingActive(actionMode, agentConfig, defaultModelConfig);
  if (isSmart) {
    const moaPresetId = actionMode === 'agent' && activeMoaPresetId ? activeMoaPresetId : null;
    return {
      modelName: null,
      moaPresetId,
      isSmartRouting: true,
    };
  }

  const selection = resolveActiveModelSelection(actionMode, agentConfig, defaultModelConfig, providers);
  let modelName: string | null = null;
  if (selection && isModelAvailable(selection, providers)) {
    modelName = selection.model;
  }

  const moaPresetId = actionMode === 'agent' && activeMoaPresetId ? activeMoaPresetId : null;
  return { modelName, moaPresetId, isSmartRouting: false };
}

/**
 * 检查模型是否可用（Provider 启用 + 有可用认证能力 + 模型在启用列表中）
 */
export function isModelAvailable(selection: SingleModelSelection, providers: ProviderConfig[]): boolean {
  const provider = providers.find((p) => p.id === selection.providerId);
  if (!provider?.isEnabled) {
    return false;
  }
  if (!hasUsableProviderAuth(provider)) {
    return false;
  }
  if (!provider.enabledModels.includes(selection.model)) {
    return false;
  }
  return true;
}
