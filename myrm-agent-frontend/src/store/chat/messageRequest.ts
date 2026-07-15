/**
 * [INPUT]
 * @/services/chat::createAISearchStream (POS: Chat streaming API client)
 * @/lib/model-binding::resolveActiveModelConfig (POS: Frontend model selection resolver)
 * @/store/useConfigStore::useConfigStore (POS: Chat configuration state store)
 *
 * [OUTPUT]
 * getModelSelection: Resolve the active model for chat requests.
 * validateChatModelConfig: Block send when default model / provider is incomplete.
 * resolveEffectiveAgentId: Resolve the agent identity used for chat memory bindings.
 * createMessageRequest: Assemble the agent chat request payload and stream it.
 * sendMessage: Submit user input into the chat stream lifecycle (sendBlocked toasts for missing chat, kanban board guard, processing lock).
 * createSmartUpdater: Route state updates to active store or background snapshot.
 * attachToChat: Re-attach to an existing multiplexed SSE stream.
 *
 * [POS]
 * Chat message request assembly layer. It prepares payloads and acts as the MMU (Memory Management Unit) routing stream updates to the correct store.
 */

import { resolveVisibleBuiltinAgentId } from '@/lib/product-surface';
import crypto from 'crypto';
import {
  Message,
  File,
  AgentConfig,
  ActionMode,
  ModelSelection,
  type BuiltinToolId,
  type ArchiveRestoreAction,
  type MentionReference,
} from '@/store/chat/types';
import useConfigStore from '../useConfigStore';
import useProviderStore from '../useProviderStore';
import useChatStore from '../useChatStore';
import { getThinkingEffort } from '@/components/features/message-input-actions/ThinkingIntensityButton';
import useAuthStore from '../useAuthStore';
import useRetrievalStore from '../useRetrievalStore';
import useQuoteStore from '../useQuoteStore';
import { showI18nToast } from '@/services/i18nToastService';
import {
  isTransientNetworkError,
  executeStreamWithRetry,
  AgentBusyError,
  FatalNetworkError,
  consumeStream,
} from './streamConsumer';
import { isRetryableHttpStatus } from '@/lib/utils/networkResilience';
import { buildMultimodalQuery } from './multimodalBuilder';
import { resolveKanbanDefaultBoardIdForRequest, resolveKanbanSendBlockReason } from '@/lib/kanban/kanbanChatBoard';
import { createAISearchStream } from '@/services/chat';
import { isCLIAgentMode, sendCLIAgentMessage } from './cliAgentMessageHandler';
import { resolveActiveModelConfig, isModelAvailable } from '@/lib/model-binding';
import { getBrowserTimezone } from '@/lib/utils/messageUtils';
import { getClientLocale, normalizeLocaleForBackend } from '@/lib/utils/localeUtils';
import { getCurrentTimestamp } from '@/lib/utils/timeUtils';
import { generateCompanion, getEnhancedPersonality, getTitle } from '@/components/features/companion/companionGenerator';
import useCompanionStore from '../useCompanionStore';
import { API_BASE_URL, fetchWithTimeout } from '@/lib/api';
import { ensureMobileE2EE, withMobilePairHeaders } from '@/lib/mobileRemote';
import { isArchiveRestoreActionInvalidError } from '@/lib/utils/networkResilience';
import { normalizeApiUrl } from '@/store/config/providerTypes';
import type { ChatState } from './types';

import type { Rarity } from '@/components/features/companion/companionGenerator';

export interface ChatActionsState {
  chatId: string | undefined;
  actionMode: ActionMode;
  searchDepth: 'normal' | 'deep';
  agentConfig: AgentConfig | null;
  abortController: AbortController | null;
  loading: boolean;
  loadingOlder: boolean;
  messages: Message[];
  compactedSummary: string | null;
  compactedBeforeId: string | null;
  workspaceDir: string | null;
  files: File[];
  mentionReferences: MentionReference[];
  cameraFrames: string[];
  hideAttachList: boolean;
  hasUsedImagesInCurrentChat: boolean;
  isGoalMode: boolean;
  goalBudgetTokens: number | null;
  goalBudgetUsd: number | null;
  goalMaxTimeSeconds: number | null;
  goalMaxTurns: number | null;
  goalProtectedPaths: string[] | null;
  goalLoopOnPause: boolean;
  goalConvergenceWindow: number | null;
  goalAcceptanceCriteria: Array<Record<string, unknown>> | null;
  goalConstraints: string[] | null;
  currentSessionMessageId: string | null;
  messageAppeared: boolean;
  isMessagesLoaded: boolean;
  hasMoreMessages: boolean;
  nextCursor: string | null;
  incognitoMode: boolean;
  sandboxMode: boolean;
  notFound: boolean;
  loadError: boolean;
  newChatCreated: boolean;
  currentBuiltinTools: BuiltinToolId[];
  regenerateSiblingGroupId?: string;
  regenerateInstruction?: string;
  clearMentionReferences: () => void;
}

export interface ChatActionsMethods {
  setMessages: (updater: (state: ChatActionsState) => void) => void;
  setLoading: (loading: boolean) => void;
  setMessageAppeared: (appeared: boolean) => void;
  setHideAttachList: (hide: boolean) => void;
  setHasUsedImagesInCurrentChat: (hasUsed: boolean) => void;
  setSelectedModels: (models: { base: string | null; vision: string | null; reasoning: string | null }) => void;
  setHasUserSelectedModel: (hasSelected: boolean) => void;
  clearCurrentSessionMessageId: () => void;
  _processSuggestions: (lastMsg: Message) => Promise<void>;
  scheduleAutoSave: () => void;
  setInputMessage: (message: string) => void;
}

const LINE_RANGE_REFERENCE_PATTERN = /^@(.+):(\d+)(?:-(\d+))?$/;

const mentionReferenceKey = (reference: MentionReference) =>
  `${reference.type}:${reference.path ?? reference.fileId ?? reference.url ?? reference.label}:${reference.startLine ?? ''}:${reference.endLine ?? ''}`;

const extractInlineMentionReferences = (input: string): MentionReference[] => {
  const references: MentionReference[] = [];
  for (const token of input.match(/@\S+/g) ?? []) {
    if (token === '@staged') {
      references.push({ type: 'git_staged', label: '@staged', source: 'special', size: null });
    } else if (token === '@diff') {
      references.push({ type: 'git_diff', label: '@diff', source: 'special', size: null });
    } else if (token === '@codebase') {
      references.push({ type: 'codebase', label: '@codebase', source: 'special', size: null });
    } else if (token.startsWith('@folder:') && token.length > '@folder:'.length) {
      const path = token.slice('@folder:'.length);
      references.push({ type: 'workspace_folder', label: token, path, source: 'workspace', size: null });
    } else if (token.startsWith('@url:') && token.length > '@url:'.length) {
      const url = token.slice('@url:'.length);
      references.push({ type: 'url', label: token, url, source: 'special', size: null });
    } else {
      const lineMatch = LINE_RANGE_REFERENCE_PATTERN.exec(token);
      if (!lineMatch) continue;
      const [, path, startRaw, endRaw] = lineMatch;
      let startLine = Number(startRaw);
      let endLine = endRaw ? Number(endRaw) : startLine;
      if (!Number.isSafeInteger(startLine) || !Number.isSafeInteger(endLine)) continue;
      if (endLine < startLine) {
        [startLine, endLine] = [endLine, startLine];
      }
      references.push({
        type: 'workspace_file',
        label: token,
        path,
        startLine,
        endLine,
        source: 'workspace',
        size: null,
      });
    }
  }
  return references;
};

const mergeMentionReferences = (selected: MentionReference[], inline: MentionReference[]): MentionReference[] => {
  const seen = new Set<string>();
  const merged: MentionReference[] = [];
  for (const reference of [...selected, ...inline]) {
    const key = mentionReferenceKey(reference);
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(reference);
  }
  return merged;
};

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

  if (!provider.apiKeys || !Array.isArray(provider.apiKeys)) return null;
  const hasActiveKey = provider.apiKeys.some((k) => k.isActive && k.key);
  if (!hasActiveKey) return null;

  const modelInfo = getModelInfo(selection.providerId, selection.model);
  const modelLevelKwargs: Record<string, unknown> = {};
  if (modelInfo?.temperature !== undefined) modelLevelKwargs.temperature = modelInfo.temperature;
  const modelExtraParams = modelInfo?.extraParams || {};
  const mergedKwargs: Record<string, unknown> = {
    temperature: resolved.temperature,
    ...resolved.modelKwargs,
    ...modelLevelKwargs,
    ...modelExtraParams,
  };

  const thinkingEffort = getThinkingEffort();
  if (thinkingEffort) {
    mergedKwargs.reasoning_effort = thinkingEffort;
  } else {
    delete mergedKwargs.reasoning_effort;
  }

  return {
    providerId: selection.providerId,
    model: selection.model,
    baseUrl: normalizeApiUrl(provider.apiUrl) || undefined,
    modelKwargs: mergedKwargs,
    supportsVision: modelInfo?.supports_vision ?? false,
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
  if (!selection) return null;

  const { providers, getModelInfo } = useProviderStore.getState();
  const provider = providers.find((p) => p.id === selection.providerId);
  if (!provider) return null;

  // if (!provider.apiKeys || !Array.isArray(provider.apiKeys)) return null;
  // if (!provider.apiKeys.some((k) => k.isActive)) return null;

  const modelInfo = getModelInfo(selection.providerId, selection.model);
  const modelLevelKwargs: Record<string, unknown> = {};
  if (modelInfo?.temperature !== undefined) modelLevelKwargs.temperature = modelInfo.temperature;
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

export const getLightModelSelection = (): ModelSelection | null => {
  const { defaultModelConfig } = useProviderStore.getState();
  const routing = defaultModelConfig?.routingConfig;
  if (!routing?.enabled) return null;
  const slotKwargs = routing.lightModel.modelKwargs ?? {};
  return resolveSelectionToModelSelection(routing.lightModel.primary, slotKwargs);
};

export const getFallbackLightModelSelection = (): ModelSelection | null => {
  const { defaultModelConfig } = useProviderStore.getState();
  const routing = defaultModelConfig?.routingConfig;
  if (!routing?.enabled) return null;
  return resolveSelectionToModelSelection(routing.lightModel.fallback);
};

export const getReasoningModelSelection = (): ModelSelection | null => {
  const { defaultModelConfig } = useProviderStore.getState();
  const routing = defaultModelConfig?.routingConfig;
  if (!routing?.enabled) return null;
  const slotKwargs = routing.reasoningModel.modelKwargs ?? {};
  return resolveSelectionToModelSelection(routing.reasoningModel.primary, slotKwargs);
};

export const getFallbackReasoningModelSelection = (): ModelSelection | null => {
  const { defaultModelConfig } = useProviderStore.getState();
  const routing = defaultModelConfig?.routingConfig;
  if (!routing?.enabled) return null;
  return resolveSelectionToModelSelection(routing.reasoningModel.fallback);
};

export const getVisionFallbackModelSelection = (): ModelSelection | null => {
  const { defaultModelConfig } = useProviderStore.getState();
  return resolveSelectionToModelSelection(defaultModelConfig?.visionFallbackModel);
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
  const hasAnyUsableProvider = providers.some((p) => p.isEnabled && p.apiKeys?.some((k) => k.isActive && k.key));
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

const validateConfig = validateChatModelConfig;

export const resolveEffectiveAgentId = (
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
  searchDepth?: 'normal' | 'deep',
): string | undefined => {
  if (actionMode === 'fast') {
    return 'builtin-fast-search';
  }
  if (actionMode === 'deep_research') {
    return resolveVisibleBuiltinAgentId(agentConfig?.agentId?.trim());
  }
  if (actionMode !== 'agent') {
    return undefined;
  }

  const explicitAgentId = agentConfig?.agentId?.trim();
  return resolveVisibleBuiltinAgentId(explicitAgentId);
};

/**
 * 创建消息请求
 *
 * API Key 不再通过 HTTP 传输。只发送 modelSelection（providerId + model），
 * 后端从 UserConfig 表读取并解密 API Key。
 */
export const createMessageRequest = async (
  input: string,
  messageId: string,
  state: ChatActionsState,
  modelSelection: ModelSelection | null,
  resumeValue?: unknown,
  archiveRestoreActions?: ArchiveRestoreAction[],
): Promise<Response> => {
  const { fetchRawWebpage, mcpConfigs, systemInstructions, enableMemory } = useConfigStore.getState();
  const { chatId, abortController, actionMode, searchDepth, agentConfig, currentBuiltinTools } = state;

  const isAgentMode = actionMode === 'agent';
  const isStreamingMode = actionMode === 'agent' || actionMode === 'fast';

  const enabledMCPConfigs = agentConfig
    ? mcpConfigs.filter((mcp) => agentConfig.selectedMcpNames.includes(mcp.name))
    : [];

  const { user } = useAuthStore.getState();
  const userId = user?.id;

  const buildUserInstructions = (): string => {
    if (!isAgentMode) {
      return systemInstructions || '';
    }

    if (!agentConfig) {
      return systemInstructions || '';
    }

    const agentPrompt = agentConfig.systemPrompt || '';
    if (agentConfig.useGlobalInstruction && systemInstructions) {
      const parts = [systemInstructions, agentPrompt].filter(Boolean);
      return parts.join('\n\n');
    }
    return agentPrompt;
  };

  let userInstructions = buildUserInstructions();
  const effectiveAgentId = resolveEffectiveAgentId(actionMode, agentConfig, searchDepth);

  const companionState = useCompanionStore.getState();
  if (companionState.enabled && !companionState.muted && userId) {
    const bones = generateCompanion(userId);
    const name = companionState.nameOverride ?? bones.defaultName;
    const effectiveRarity: Rarity = (companionState.evolvedRarity ?? bones.rarity) as Rarity;
    const personality = getEnhancedPersonality(bones, effectiveRarity);
    const title = getTitle(bones.peakStat, effectiveRarity);
    const displayName = title ? `${title} ${name}` : name;
    const intro = `\n# Companion\nA ${effectiveRarity} ${bones.species} named ${displayName} sits beside the user. Personality: ${personality}. It's a separate observer with its own speech bubble — you are NOT ${name}. If the user addresses ${name}, respond in ≤1 line; don't narrate what ${name} might say.`;
    userInstructions = userInstructions ? userInstructions + intro : intro;
  }

  const liteModelSelection = getLiteModelSelection();
  const fallbackModelSelection = getFallbackModelSelection(actionMode, agentConfig);
  const safetyFallbackModelSelection = getSafetyFallbackModelSelection(actionMode, agentConfig);
  const fallbackLiteModelSelection = getFallbackLiteModelSelection();
  const lightModelSelection = getLightModelSelection();
  const fallbackLightModelSelection = getFallbackLightModelSelection();
  const reasoningModelSelection = getReasoningModelSelection();
  const fallbackReasoningModelSelection = getFallbackReasoningModelSelection();
  const visionFallbackModelSelection = getVisionFallbackModelSelection();

  const query = await buildMultimodalQuery(input, state.files, state.cameraFrames);

  // Prioritize locale from personalSettings, fallback to cookie
  const configStore = useConfigStore.getState();
  const savedLocale = configStore.personalSettings?.locale;
  const cookieLocale = getClientLocale();
  const userLocale = normalizeLocaleForBackend(savedLocale || cookieLocale);

  const kanbanDefaultBoardId = resolveKanbanDefaultBoardIdForRequest(currentBuiltinTools);

  const requestBody = {
    query,
    message_id: messageId,
    chat_id: chatId!,
    action_mode: actionMode,
    multiplexed: true,
    ...(actionMode === 'fast' && searchDepth && { search_depth: searchDepth }),
    ...(state.isWorkflowMode && { use_workflow: true }),
    ...(resumeValue !== undefined && { resume_value: resumeValue }),
    ...(archiveRestoreActions && archiveRestoreActions.length > 0
      ? {
          archive_restore_actions: archiveRestoreActions.map((action) => ({
            type: action.type,
            restore_arg: action.restoreArg,
          })),
        }
      : {}),
    ...(modelSelection && { model_selection: modelSelection }),
    timezone: configStore.timezone || getBrowserTimezone(),
    timestamp: getCurrentTimestamp(),
    ...(userLocale && { locale: userLocale }),
    ...(effectiveAgentId && { agent_id: effectiveAgentId }),
    ...(agentConfig?.ephemeralSubagents && { ephemeral_subagents: agentConfig.ephemeralSubagents }),
    ...(userInstructions && { user_instructions: userInstructions }),
    ...(liteModelSelection && { lite_model_selection: liteModelSelection }),
    ...(fallbackModelSelection && { fallback_model_selection: fallbackModelSelection }),
    ...(safetyFallbackModelSelection && { safety_fallback_model_selection: safetyFallbackModelSelection }),
    ...(fallbackLiteModelSelection && {
      fallback_lite_model_selection: fallbackLiteModelSelection,
    }),
    ...(lightModelSelection && { light_model_selection: lightModelSelection }),
    ...(fallbackLightModelSelection && {
      fallback_light_model_selection: fallbackLightModelSelection,
    }),
    ...(reasoningModelSelection && { reasoning_model_selection: reasoningModelSelection }),
    ...(fallbackReasoningModelSelection && {
      fallback_reasoning_model_selection: fallbackReasoningModelSelection,
    }),
    ...(visionFallbackModelSelection && { vision_fallback_model_selection: visionFallbackModelSelection }),
    ...(isAgentMode && enabledMCPConfigs.length > 0 && { mcp_cfg: enabledMCPConfigs }),
    ...(isAgentMode && { fetch_raw_webpage: fetchRawWebpage }),
    ...(isStreamingMode && { enable_memory: enableMemory }),
    ...(isStreamingMode && {
      memory_require_confirmation: useConfigStore.getState().memoryRequireConfirmation,
    }),
    ...(isStreamingMode && {
      enable_memory_auto_extraction: useConfigStore.getState().enableMemoryAutoExtraction,
      enable_conversation_search: useConfigStore.getState().memoryEnableConversationSearch,
      incognito_mode: useChatStore.getState().incognitoMode,
      ...(useChatStore.getState().sandboxMode && { sandbox_mode: true }),
    }),
    ...(isStreamingMode && {
      pre_compact_enabled: useConfigStore.getState().preCompactEnabled,
    }),
    ...(isStreamingMode && {
      pre_compact_budget_tokens: useConfigStore.getState().preCompactBudgetTokens,
    }),
    ...(isAgentMode && {
      enable_advanced_retrieval: useRetrievalStore.getState().enableAdvancedRetrieval ?? false,
    }),
    ...(isAgentMode && {
      agent_config: {
        skill_ids: agentConfig?.selectedSkillIds ?? [],
        skill_configs: agentConfig?.skillConfigs,
        enabled_builtin_tools: currentBuiltinTools,
        browser_source: agentConfig?.browserSource,
        dialog_policy: agentConfig?.dialogPolicy,
        session_recording: agentConfig?.sessionRecording,
        auto_restore_domains: agentConfig?.autoRestoreDomains ?? [],
        ...(kanbanDefaultBoardId && { kanban_default_board_id: kanbanDefaultBoardId }),
      },
    }),
    ...(isAgentMode &&
      agentConfig?.forceDelegateAgent && {
        force_delegate_agent: agentConfig.forceDelegateAgent,
      }),
    ...(isStreamingMode &&
      useConfigStore.getState().privacyEnabled && {
        privacy_enabled: true,
        privacy_s2_action: useConfigStore.getState().privacyS2Action,
        privacy_s3_action: useConfigStore.getState().privacyS3Action,
        ...(useConfigStore.getState().privacyRouting?.localModel && {
          privacy_routing: useConfigStore.getState().privacyRouting,
        }),
        ...(useConfigStore.getState().privacyCustomKeywordsS2?.length && {
          privacy_custom_keywords_s2: useConfigStore.getState().privacyCustomKeywordsS2,
        }),
        ...(useConfigStore.getState().privacyCustomKeywordsS3?.length && {
          privacy_custom_keywords_s3: useConfigStore.getState().privacyCustomKeywordsS3,
        }),
        ...(useConfigStore.getState().privacyCustomPatternsS2?.length && {
          privacy_custom_patterns_s2: useConfigStore.getState().privacyCustomPatternsS2,
        }),
        ...(useConfigStore.getState().privacyCustomPatternsS3?.length && {
          privacy_custom_patterns_s3: useConfigStore.getState().privacyCustomPatternsS3,
        }),
        ...(useConfigStore.getState().privacySensitiveToolsS2?.length && {
          privacy_sensitive_tools_s2: useConfigStore.getState().privacySensitiveToolsS2,
        }),
        ...(useConfigStore.getState().privacySensitiveToolsS3?.length && {
          privacy_sensitive_tools_s3: useConfigStore.getState().privacySensitiveToolsS3,
        }),
        ...(useConfigStore.getState().privacyDeepScan && {
          privacy_deep_scan: true,
        }),
      }),
    ...(state.regenerateSiblingGroupId ? { sibling_group_id: state.regenerateSiblingGroupId } : {}),
    ...(state.regenerateInstruction ? { regenerate_instruction: state.regenerateInstruction } : {}),
    ...(state.isGoalMode && {
      goal: {
        ...(state.goalBudgetTokens != null && { max_tokens: state.goalBudgetTokens }),
        ...(state.goalBudgetUsd != null && { max_usd: state.goalBudgetUsd }),
        ...(state.goalMaxTimeSeconds != null && { max_time_seconds: state.goalMaxTimeSeconds }),
        ...(state.goalMaxTurns != null && { max_turns: state.goalMaxTurns }),
        ...(state.goalConvergenceWindow != null && { convergence_window: state.goalConvergenceWindow }),
        ...(state.goalLoopOnPause && { loop_on_pause: true }),
        ...(state.goalAcceptanceCriteria &&
          state.goalAcceptanceCriteria.length > 0 && { acceptance_criteria: state.goalAcceptanceCriteria }),
        ...(() => {
          const filtered = state.goalConstraints?.filter((c) => c.trim().length > 0);
          return filtered && filtered.length > 0 ? { constraints: filtered } : {};
        })(),
        ...(() => {
          const filtered = state.goalProtectedPaths?.filter((p) => p.trim().length > 0);
          return filtered && filtered.length > 0 ? { protected_paths: filtered } : {};
        })(),
      },
    }),
    ...(() => {
      const references = mergeMentionReferences(state.mentionReferences, extractInlineMentionReferences(input));
      if (references.length === 0) return {};
      
      const fileReferences = references.filter(r => r.type !== 'agent');
      const agentReferences = references.filter(r => r.type === 'agent');
      
      const payload: Record<string, any> = {};
      if (fileReferences.length > 0) {
        payload.mention_references = fileReferences.map((reference) => ({
          type: reference.type,
          path: reference.path,
          file_id: reference.fileId,
          url: reference.url,
          label: reference.label,
          start_line: reference.startLine,
          end_line: reference.endLine,
          ...(reference.conceptName ? { concept_name: reference.conceptName } : {}),
        }));
      }
      if (agentReferences.length > 0) {
        payload.mentioned_agent_ids = agentReferences.map(r => r.fileId).filter(Boolean);
      }
      return payload;
    })(),
    ...(() => {
      const fileIds = state.files.map((f) => f.id).filter(Boolean) as string[];
      return fileIds.length > 0 ? { uploaded_file_ids: fileIds } : {};
    })(),
  };

  state.clearMentionReferences();

  const quoteState = useQuoteStore.getState();
  if (quoteState.quote) {
    Object.assign(requestBody, {
      quote: {
        source_message_id: quoteState.quote.sourceMessageId,
        quoted_text: quoteState.quote.quotedText,
      },
    });
    quoteState.clearQuote();
  }

  return createAISearchStream(requestBody, abortController || undefined);
};

/**
 * 发送消息主函数
 */
import useToolApprovalStore from '../useToolApprovalStore';

import { produce } from 'immer';
import useWorkspaceStore from '../useWorkspaceStore';

export const createSmartUpdater = (chatId: string | undefined, originalSetMessages: (updater: (state: ChatActionsState) => void) => void) => {
  return (updater: (state: ChatActionsState) => void) => {
    if (!chatId) {
      originalSetMessages(updater);
      return;
    }

    const workspaceState = useWorkspaceStore.getState();
    if (workspaceState.panes.length === 0) {
      originalSetMessages(updater);
      return;
    }

    const activePane = workspaceState.panes.find((p: any) => p.id === workspaceState.activePaneId);

    if (activePane && activePane.chatId === chatId) {
      originalSetMessages(updater);
      return;
    }

    const pane = workspaceState.panes.find((p: any) => p.chatId === chatId);
    if (pane) {
      const currentSnapshot = pane.snapshot || { messages: [], loading: false, messageAppeared: false, hideAttachList: false, hasUsedImagesInCurrentChat: false };
      const nextSnapshot = produce(currentSnapshot, (draft: any) => {
        updater(draft as ChatActionsState);
      });
      useWorkspaceStore.getState().savePaneSnapshot(pane.id, nextSnapshot);
      return;
    }

    originalSetMessages(updater);
  };
};

export const sendMessage = async (
  input: string,
  messageId: string | undefined,
  state: ChatActionsState,
  actions: ChatActionsMethods,
  getCurrentSessionMessageId: () => string,
  resumeValue?: unknown,
  archiveRestoreActions?: ArchiveRestoreAction[],
): Promise<void> => {
  if (state.loading) {
    showI18nToast('chat.messageFailed.title', undefined, {
      descriptionKey: 'chat.messageFailed.description',
      descriptionValues: { error: 'Please wait for the current message to finish' },
      type: 'warning',
      duration: 3000,
    });
    return;
  }

  if (!state.chatId?.trim()) {
    showI18nToast('chat.sendBlocked.title', undefined, {
      descriptionKey: 'chat.sendBlocked.noChatDescription',
      type: 'warning',
      duration: 5000,
    });
    return;
  }

  if (state.actionMode === 'agent' && state.currentBuiltinTools.includes('kanban')) {
    const kanbanBlockReason = await resolveKanbanSendBlockReason(state.currentBuiltinTools);
    if (kanbanBlockReason) {
      showI18nToast('chat.sendBlocked.title', undefined, {
        descriptionKey:
          kanbanBlockReason === 'no_boards'
            ? 'chat.sendBlocked.kanbanNoBoardDescription'
            : 'chat.sendBlocked.kanbanNeedBoardDescription',
        type: 'warning',
        duration: 5000,
      });
      return;
    }
  }

  useChatStore.getState().clearPendingGapRetry();

  const requestMessageId = messageId ?? getCurrentSessionMessageId();

  // 防重锁：检查该消息是否正在被处理（通过按钮审批或其他文本审批）
  if (useToolApprovalStore.getState().isProcessing(requestMessageId)) {
    showI18nToast('chat.sendBlocked.title', undefined, {
      descriptionKey: 'chat.sendBlocked.processingDescription',
      type: 'warning',
      duration: 4000,
    });
    return;
  }

  // 标记为正在处理，防止并发
  useToolApprovalStore.getState().markProcessing(requestMessageId);

  let userMessageId: string | undefined;

  try {
    // ============================================================================
    // CLI Agent 模式检测和处理 (Claude Code)
    // ============================================================================
    if (isCLIAgentMode(state.actionMode)) {
      actions.setLoading(true);

      await sendCLIAgentMessage(
        input,
        {
          messages: state.messages,
          chatId: state.chatId,
          loading: state.loading,
          messageAppeared: state.messageAppeared,
          agentConfig: state.agentConfig,
        },
        {
          setMessages: actions.setMessages,
          setLoading: actions.setLoading,
          setMessageAppeared: actions.setMessageAppeared,
          scheduleAutoSave: actions.scheduleAutoSave,
          setInputMessage: actions.setInputMessage,
        },
      );

      return;
    }

    // 搜索服务检查：
    // - 快速搜索/深度研究模式：严格要求搜索服务，否则拦截
    // - agent 模式：web_search 工具可选，如果没有配置仅警告，不拦截（后端会处理）
    const requiresSearch = state.actionMode === 'fast' || state.actionMode === 'deep_research';
    const wantsSearch = state.actionMode === 'agent' && state.currentBuiltinTools.includes('web_search');

    if (requiresSearch || wantsSearch) {
      const { guardSearchServiceConfigured } = await import('@/store/config/searchService');
      const { searchServiceConfigs } = useConfigStore.getState();
      const searchServiceOk = guardSearchServiceConfigured(searchServiceConfigs);

      if (!searchServiceOk) {
        if (requiresSearch) {
          // 快速搜索/深度研究模式：必须有搜索服务，拦截请求
          return;
        } else {
          // agent 模式：仅警告，不拦截（web_search 工具在执行时会优雅降级）
          console.warn(
            '[WARN] web_search tool enabled but search service not configured. Tool will be skipped during execution.',
          );
        }
      }
    }

    // 验证配置
    const { valid, modelSelection } = validateConfig(state.actionMode, state.agentConfig);
    if (!valid) {
      return;
    }

    // Auto-reset workflow mode after sending to prevent accidental high-cost subsequent messages
    if (state.isWorkflowMode) {
      actions.setIsWorkflowMode(false);
    }

    // 创建 AbortController 并设置 loading 状态
    const abortController = new AbortController();
    
    // Save the abort controller to the workspace store for the current pane
    if (state.chatId) {
      const paneId = useWorkspaceStore.getState().panes.find((p: any) => p.chatId === state.chatId)?.id;
      if (paneId) {
        useWorkspaceStore.getState().setPaneAbortController(paneId, abortController);
      }
    }

    const smartSetMessages = createSmartUpdater(state.chatId, actions.setMessages);
    const smartActions = { ...actions, setMessages: smartSetMessages };

    smartActions.setMessages((innerState) => {
      innerState.loading = true;
      innerState.messageAppeared = false;
      innerState.abortController = abortController;
    });

    let added = false;
    let recievedMessage = '';

    const isRegenerate = !!state.regenerateSiblingGroupId;

    // 生成用户消息 ID
    userMessageId = (() => {
      const timestamp = Date.now().toString(36);
      const microTime = (performance.now() * 1000).toString(36).replace('.', '');
      const randomBytes = crypto.randomBytes(6).toString('hex');
      const counter = ((Math.random() * 0xffff) | 0).toString(36);
      return `u-${timestamp}-${microTime}-${randomBytes}-${counter}`;
    })();

    const persistFiles = state.files.length > 0 ? state.files.map(({ contentHash: _, ...rest }) => rest) : undefined;

    if (!isRegenerate && !resumeValue) {
      smartActions.setMessages((innerState) => {
        innerState.messages.push({
          content: input,
          messageId: userMessageId,
          chatId: innerState.chatId!,
          role: 'user',
          createdAt: new Date(),
          files: persistFiles,
        });
      });
    }

    await executeStreamWithRetry(
      input,
      requestMessageId,
      state,
      smartActions,
      modelSelection,
      abortController,
      added,
      recievedMessage,
      resumeValue,
      archiveRestoreActions,
    );
    useCompanionStore.getState().incrementConversation();
  } catch (error) {
    const smartSetMessages = createSmartUpdater(state.chatId, actions.setMessages);
    
    if (error instanceof AgentBusyError) {
      // Let the UI handle requeueing
      throw error;
    }
    if (isArchiveRestoreActionInvalidError(error)) {
      if (userMessageId) {
        smartSetMessages((innerState) => {
          const lastMessageIndex = innerState.messages.length - 1;
          if (lastMessageIndex >= 0 && innerState.messages[lastMessageIndex].messageId === userMessageId) {
            innerState.messages.pop();
          }
        });
      }
      showI18nToast('chat.archiveRestore.invalidTitle', undefined, {
        descriptionKey: 'chat.archiveRestore.invalidDescription',
        descriptionValues: { error: error.detail || error.message },
        type: 'error',
        duration: 6000,
      });
      throw error;
    }
    if (error instanceof Error && error.name !== 'AbortError') {
      const isNetworkError = isTransientNetworkError(error);

      if (isNetworkError && userMessageId) {
        smartSetMessages((innerState) => {
          const msg = innerState.messages.find((m) => m.messageId === userMessageId);
          if (msg) msg.sendFailed = true;
        });
      } else if (userMessageId) {
        smartSetMessages((innerState) => {
          const lastMessageIndex = innerState.messages.length - 1;
          if (lastMessageIndex >= 0 && innerState.messages[lastMessageIndex].messageId === userMessageId) {
            innerState.messages.pop();
          }
        });
      }

      showI18nToast('chat.messageFailed.title', undefined, {
        descriptionKey: isNetworkError ? 'chat.messageFailed.networkError' : 'chat.messageFailed.description',
        descriptionValues: isNetworkError ? undefined : { error: error.message },
        type: 'error',
        duration: isNetworkError ? 8000 : 3000,
      });
    }
  } finally {
    const smartSetMessages = createSmartUpdater(state.chatId, actions.setMessages);
    smartSetMessages((innerState) => {
      innerState.loading = false;
      innerState.abortController = null;
      innerState.currentSessionMessageId = null;
      innerState.files = [];
      innerState.cameraFrames = [];
    });
    
    if (state.chatId) {
      const paneId = useWorkspaceStore.getState().panes.find((p: any) => p.chatId === state.chatId)?.id;
      if (paneId) {
        useWorkspaceStore.getState().setPaneAbortController(paneId, null);
      }
    }

    actions.setHideAttachList(false);
    actions.clearCurrentSessionMessageId();
    actions.scheduleAutoSave();

    // Always release the processing lock on finally
    useToolApprovalStore.getState().unmarkProcessing(requestMessageId);
  }
};

export const attachToChat = async (
  chatId: string,
  actions: ChatActionsMethods,
  get: () => ChatState,
): Promise<boolean> => {
  const state = get();
  if (state.loading) {
    return false;
  }

  const smartSetMessages = createSmartUpdater(chatId, actions.setMessages);
  const smartActions = { ...actions, setMessages: smartSetMessages };

  const abortController = new AbortController();

  const paneId = useWorkspaceStore.getState().panes.find((p: any) => p.chatId === chatId)?.id;
  if (paneId) {
    useWorkspaceStore.getState().setPaneAbortController(paneId, abortController);
  }

  smartActions.setMessages((draft) => {
    draft.loading = true;
    draft.abortController = abortController;
  });

  try {
    await ensureMobileE2EE();
    const token = typeof window !== 'undefined' ? localStorage.getItem('auth_token') : null;
    const headers = withMobilePairHeaders({
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    });

    const response = await fetchWithTimeout(
      `/agents/chat/${chatId}/attach`,
      {
        method: 'GET',
        headers,
        signal: abortController.signal,
      },
      0,
    );

    if (!response.ok) {
      if (response.status === 404) {
        // No active task
        return false;
      }
      if (!isRetryableHttpStatus(response.status)) {
        throw new FatalNetworkError(`Attach failed: ${response.statusText}`, response.status);
      }
      throw new Error(`Attach failed: ${response.statusText}`);
    }

    if (!response.body) {
      return false;
    }
    
    await consumeStream(response, '', state, smartActions, abortController, false, '');
    return true;
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      console.log('Attach stream aborted');
    } else {
      console.error('Attach stream error:', error);
      throw error;
    }
    return false;
  } finally {
    smartActions.setMessages((draft) => {
      draft.loading = false;
      draft.abortController = null;
    });
    if (paneId) {
      useWorkspaceStore.getState().setPaneAbortController(paneId, null);
    }
  }
};
