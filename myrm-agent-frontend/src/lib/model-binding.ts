/**
 * [INPUT]
 * @/lib/model-routing::resolveSmartRouting (POS: Single decision point for smart routing activation and slots)
 * @/store/chat/types::ActionMode, AgentConfig (POS: 会话级 Agent 与模式配置类型)
 * @/store/config/providerTypes::DefaultModelConfig, ProviderConfig, hasUsableProviderAuth (POS: Provider and default-model configuration contract)
 *
 * [OUTPUT]
 * resolveActiveModelSelection / resolveActiveModelConfig / resolveActiveFallbackSelection: 按 actionMode 与智能体绑定解析活动模型、完整配置与备用模型。
 * resolveModelPickerTriggerDisplay: 模型选择器触发器展示（模型名、MoA preset、Smart Routing 态与可选性）。
 * isModelAvailable: 模型可用性（Provider 启用 + 有可用认证 + 模型在启用列表中）。
 *
 * [POS]
 * 模型绑定解析层：根据 actionMode 与智能体配置解析应使用的模型，优先级链为 模式/智能体绑定 > 全局默认；路由判定委托 model-routing。
 */

import type { ActionMode, AgentConfig } from '@/store/chat/types';
import type {
  CustomModelInfo,
  DefaultModelConfig,
  SingleModelSelection,
  ProviderConfig,
} from '@/store/config/providerTypes';
import { hasUsableProviderAuth } from '@/store/config/providerTypes';
import { resolveSmartRouting } from '@/lib/model-routing';

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
 * Model picker trigger display: primary model name plus optional session MoA preset chip and smart routing flags.
 */
export interface ModelPickerTriggerDisplay {
  modelName: string | null;
  moaPresetId: string | null;
  /** Complexity routing drives this turn (the trigger shows "Auto" instead of a model name). */
  isSmartRouting: boolean;
  /** The picker may offer the "Smart Routing" entry; selecting it clears the agent's pinned model. */
  canSelectSmartRouting: boolean;
}

export function resolveModelPickerTriggerDisplay(
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
  defaultModelConfig: DefaultModelConfig,
  providers: ProviderConfig[],
  customModelInfo: Record<string, CustomModelInfo>,
  activeMoaPresetId: string | null,
): ModelPickerTriggerDisplay {
  const routing = resolveSmartRouting(actionMode, agentConfig, defaultModelConfig, providers, customModelInfo);
  const moaPresetId = actionMode === 'agent' && activeMoaPresetId ? activeMoaPresetId : null;
  if (routing.active) {
    return { modelName: null, moaPresetId, isSmartRouting: true, canSelectSmartRouting: routing.canSelect };
  }

  const selection = resolveActiveModelSelection(actionMode, agentConfig, defaultModelConfig, providers);
  let modelName: string | null = null;
  if (selection && isModelAvailable(selection, providers)) {
    modelName = selection.model;
  }

  return { modelName, moaPresetId, isSmartRouting: false, canSelectSmartRouting: routing.canSelect };
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
