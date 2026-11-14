/**
 * [INPUT]
 * @/lib/model-binding::resolveActiveModelConfig (POS: Frontend model selection resolver)
 * @/lib/model-routing::resolveSmartRouting (POS: Single decision point for smart routing activation and slots)
 * @/store/useProviderStore::useProviderStore (POS: Provider and default model configuration store)
 *
 * [OUTPUT]
 * getModelSelection: Resolve the active model for chat requests.
 * getRoutingModelSelections: Resolve the light / reasoning routing slots a request carries (empty when smart routing does not apply).
 * get*ModelSelection / get*Fallback*ModelSelection: Resolve the lite, fallback, safety, vision, code and long-document slots.
 * getAutoMoaReasoning / getAutoMoaPresetId: Resolve the automatic MoA reasoning switch and preset.
 * validateChatModelConfig: Block send when default model / provider is incomplete.
 *
 * [POS]
 * Model slot resolution of the message request: turns the user's provider configuration into the model selections a request carries.
 */

import { getThinkingEffort } from '@/components/features/message-input-actions/ThinkingIntensityButton';
import { isModelAvailable, resolveActiveModelConfig } from '@/lib/model-binding';
import { resolveSmartRouting } from '@/lib/model-routing';
import { showI18nToast } from '@/services/i18nToastService';
import type { ActionMode, AgentConfig, ModelSelection } from '@/store/chat/types';
import { hasUsableProviderAuth, normalizeApiUrl, supportsProviderNoAuth } from '@/store/config/providerTypes';
import useProviderStore from '../useProviderStore';

/**
 * 获取基础模型选择信息（不含 API Key）
 *
 * 根据当前 actionMode 和智能体配置解析活动模型：
 * - fast 模式：优先 fastModeModel，回退 baseModel
 * - agent 模式：优先智能体绑定模型，回退 baseModel
 * - 其他模式：使用 baseModel
 */
export const getModelSelection = (actionMode: ActionMode, agentConfig: AgentConfig | null): ModelSelection | null => {
  const { defaultModelConfig, providers, getModelInfo } = useProviderStore.getState();

  const resolved = resolveActiveModelConfig(actionMode, agentConfig, defaultModelConfig, providers);
  const { selection } = resolved;
  if (!selection) {
    return null;
  }

  const provider = providers.find((p) => p.id === selection.providerId);
  if (!provider) {
    return null;
  }

  const hasActiveKey = provider.apiKeys?.some((k) => k.isActive && k.key) || Boolean(provider.oauthConnected);
  if (!hasActiveKey && !supportsProviderNoAuth(provider)) {
    return null;
  }

  const modelInfo = getModelInfo(selection.providerId, selection.model);
  const modelLevelKwargs: Record<string, unknown> = {};
  if (modelInfo?.temperature !== undefined) {
    modelLevelKwargs.temperature = modelInfo.temperature;
  }
  const modelExtraParams = modelInfo?.extraParams || {};
  const mergedKwargs: Record<string, unknown> = {
    temperature: resolved.temperature,
    ...resolved.modelKwargs,
    ...modelLevelKwargs,
    ...modelExtraParams,
  };

  // The picker's `auto` carries no choice, so a depth configured on the model stays; any other choice replaces it.
  const thinkingEffort = getThinkingEffort();
  if (thinkingEffort) {
    mergedKwargs.reasoning_effort = thinkingEffort;
  }

  const activeKeyCount = provider.apiKeys.filter((k) => k.isActive && k.key).length;

  return {
    providerId: selection.providerId,
    model: selection.model,
    baseUrl: normalizeApiUrl(provider.apiUrl) || undefined,
    modelKwargs: mergedKwargs,
    supportsVision: modelInfo?.supports_vision ?? false,
    credentialPoolStrategy: activeKeyCount > 1 ? provider.credentialPoolStrategy : undefined,
  };
};

/**
 * Resolve a SingleModelSelection into a ModelSelection (with provider validation).
 * Shared by primary and fallback model resolution.
 */
const resolveSelectionToModelSelection = (
  selection: import('@/store/config/providerTypes').SingleModelSelection | null | undefined,
  extraKwargs?: Record<string, unknown>,
): ModelSelection | null => {
  if (!selection) {
    return null;
  }

  const { providers, getModelInfo } = useProviderStore.getState();
  const provider = providers.find((p) => p.id === selection.providerId);
  if (!provider) {
    return null;
  }

  // if (!provider.apiKeys || !Array.isArray(provider.apiKeys)) return null;
  // if (!provider.apiKeys.some((k) => k.isActive)) return null;

  const modelInfo = getModelInfo(selection.providerId, selection.model);
  const modelLevelKwargs: Record<string, unknown> = {};
  if (modelInfo?.temperature !== undefined) {
    modelLevelKwargs.temperature = modelInfo.temperature;
  }
  const modelExtraParams = modelInfo?.extraParams || {};
  const mergedKwargs = { ...extraKwargs, ...modelLevelKwargs, ...modelExtraParams };

  return {
    providerId: selection.providerId,
    model: selection.model,
    baseUrl: normalizeApiUrl(provider.apiUrl) || undefined,
    modelKwargs: Object.keys(mergedKwargs).length > 0 ? mergedKwargs : undefined,
    supportsVision: modelInfo?.supports_vision ?? false,
  };
};

export const getLiteModelSelection = (): ModelSelection | null => {
  const { defaultModelConfig } = useProviderStore.getState();
  const globalModelKwargs = defaultModelConfig.liteModel.modelKwargs ?? {};
  return resolveSelectionToModelSelection(defaultModelConfig?.liteModel?.primary, globalModelKwargs);
};

export const getFallbackModelSelection = (
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
): ModelSelection | null => {
  if (actionMode === 'agent' && agentConfig?.fallbackModelSelection) {
    return resolveSelectionToModelSelection(agentConfig.fallbackModelSelection);
  }
  const { defaultModelConfig } = useProviderStore.getState();
  return resolveSelectionToModelSelection(defaultModelConfig?.baseModel?.fallback);
};

export const getSafetyFallbackModelSelection = (
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
): ModelSelection | null => {
  if (actionMode === 'agent' && agentConfig?.safetyFallbackModelSelection) {
    return resolveSelectionToModelSelection(agentConfig.safetyFallbackModelSelection);
  }
  // The system doesn't have a default safety fallback yet in defaultModelConfig
  return null;
};

export const getFallbackLiteModelSelection = (): ModelSelection | null => {
  const { defaultModelConfig } = useProviderStore.getState();
  return resolveSelectionToModelSelection(defaultModelConfig?.liteModel?.fallback);
};

export interface RoutingModelSelections {
  light: ModelSelection | null;
  fallbackLight: ModelSelection | null;
  reasoning: ModelSelection | null;
  fallbackReasoning: ModelSelection | null;
}

const NO_ROUTING_SELECTIONS: RoutingModelSelections = {
  light: null,
  fallbackLight: null,
  reasoning: null,
  fallbackReasoning: null,
};

/**
 * Light / reasoning slots sent with the request. Empty unless smart routing applies to this turn, so the
 * server never routes a turn that the UI presents as un-routed (see `resolveSmartRouting`).
 */
export const getRoutingModelSelections = (
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
): RoutingModelSelections => {
  const { providers, customModelInfo, defaultModelConfig } = useProviderStore.getState();
  const routing = resolveSmartRouting(actionMode, agentConfig, defaultModelConfig, providers, customModelInfo);
  if (!routing.active) {
    return NO_ROUTING_SELECTIONS;
  }
  return {
    light: resolveSelectionToModelSelection(routing.light.primary, routing.light.modelKwargs),
    fallbackLight: resolveSelectionToModelSelection(routing.light.fallback),
    reasoning: resolveSelectionToModelSelection(routing.reasoning.primary, routing.reasoning.modelKwargs),
    fallbackReasoning: resolveSelectionToModelSelection(routing.reasoning.fallback),
  };
};

export const getVisionFallbackModelSelection = (): ModelSelection | null => {
  const { defaultModelConfig } = useProviderStore.getState();
  return resolveSelectionToModelSelection(defaultModelConfig?.visionFallbackModel?.primary);
};

export const getCodeModelSelection = (): ModelSelection | null => {
  const { defaultModelConfig } = useProviderStore.getState();
  return resolveSelectionToModelSelection(defaultModelConfig?.codeModel?.primary);
};

export const getFallbackCodeModelSelection = (): ModelSelection | null => {
  const { defaultModelConfig } = useProviderStore.getState();
  return resolveSelectionToModelSelection(defaultModelConfig?.codeModel?.fallback);
};

export const getLongDocModelSelection = (): ModelSelection | null => {
  const { defaultModelConfig } = useProviderStore.getState();
  return resolveSelectionToModelSelection(defaultModelConfig?.longDocModel?.primary);
};

export const getFallbackLongDocModelSelection = (): ModelSelection | null => {
  const { defaultModelConfig } = useProviderStore.getState();
  return resolveSelectionToModelSelection(defaultModelConfig?.longDocModel?.fallback);
};

export const getAutoMoaReasoning = (agentConfig?: AgentConfig | null): boolean => {
  const agentOverlay = agentConfig?.engineParams?.moa_overlay as Record<string, unknown> | undefined;
  if (typeof agentOverlay?.auto_on_reasoning === 'boolean') {
    return agentOverlay.auto_on_reasoning;
  }
  const { defaultModelConfig } = useProviderStore.getState();
  return Boolean(defaultModelConfig?.routingConfig?.autoMoaReasoning);
};

export const getAutoMoaPresetId = (agentConfig?: AgentConfig | null): string | undefined => {
  const { defaultModelConfig } = useProviderStore.getState();
  return defaultModelConfig?.routingConfig?.autoMoaPresetId;
};

/**
 * 检查聊天模型配置是否完整（与 Server model_resolver 对齐，无 env fallback）。
 */
export const validateChatModelConfig = (
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
): { valid: boolean; modelSelection: ModelSelection | null } => {
  const modelSelection = getModelSelection(actionMode, agentConfig);
  if (modelSelection) {
    return { valid: true, modelSelection };
  }

  const { defaultModelConfig, providers } = useProviderStore.getState();
  const hasAnyUsableProvider = providers.some((p) => p.isEnabled && hasUsableProviderAuth(p));
  const primary = defaultModelConfig?.baseModel?.primary;
  const missingDefaultOnly = hasAnyUsableProvider && (!primary || !isModelAvailable(primary, providers));

  showI18nToast('chat.modelNotConfigured.title', undefined, {
    descriptionKey: missingDefaultOnly
      ? 'chat.defaultModelNotConfigured.description'
      : 'chat.modelNotConfigured.description',
    type: 'warning',
    duration: 6000,
    action: {
      label: missingDefaultOnly ? 'chat.defaultModelNotConfigured.action' : 'chat.modelNotConfigured.action',
      onClick: () => {
        window.location.href = missingDefaultOnly ? '/settings/defaultModel' : '/settings/models';
      },
    },
  });
  return { valid: false, modelSelection: null };
};
