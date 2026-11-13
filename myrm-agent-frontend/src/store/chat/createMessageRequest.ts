/**
 * [INPUT]
 * @/services/chat::createAISearchStream (POS: Chat streaming API client)
 * ./modelSelection (POS: Model slot resolution)
 * ./mentionReferences (POS: Mention reference rules)
 * ./requestInstructions (POS: The client's share of user_instructions)
 *
 * [OUTPUT]
 * resolveEffectiveAgentId: Resolve the agent identity used for chat memory bindings.
 * createMessageRequest: Assemble the agent chat request payload and stream it.
 *
 * [POS]
 * Chat message request assembly: reads the stores a turn depends on, builds the request body and opens the stream.
 */

import { buildMultimodalQuery } from './multimodalBuilder';
import { resolveVisibleBuiltinAgentId } from '@/lib/product-surface';
import type {
  ActionMode,
  AgentConfig,
  ArchiveRestoreAction,
  ModelSelection,
  TurnCapabilityTerminalTelemetry,
} from '@/store/chat/types';
import useConfigStore from '../useConfigStore';
import { buildPrivacyRoutingRequest } from '@/store/config/privacyRoutingSecret';
import useChatStore from '../useChatStore';
import { useScopedArtifactStore } from '../useScopedArtifactStore';
import useAuthStore from '../useAuthStore';
import useRetrievalStore from '../useRetrievalStore';
import useQuoteStore from '../useQuoteStore';
import { resolveKanbanDefaultBoardIdForRequest } from '@/lib/kanban/kanbanChatBoard';
import { createAISearchStream } from '@/services/chat';
import { getBrowserTimezone } from '@/lib/utils/messageUtils';
import { getClientLocale, normalizeLocaleForBackend } from '@/lib/utils/locale';
import { getCurrentTimestamp } from '@/lib/utils/timeUtils';
import { normalizeMCPServiceConfigs } from '@/lib/utils/mcp-config';
import { consumeMigrationReadinessAnchorForAgent, peekMigrationBoundProjectId } from '@/lib/migrationChatHandoff';
import type { ChatActionsState } from './chatActions';
import { resolveKanbanProjectScope } from './kanbanProjectScope';
import { buildMentionPayload } from './mentionReferences';
import { buildClientInstructions } from './requestInstructions';
import {
  getAutoMoaPresetId,
  getAutoMoaReasoning,
  getCodeModelSelection,
  getFallbackCodeModelSelection,
  getFallbackLiteModelSelection,
  getFallbackLongDocModelSelection,
  getFallbackModelSelection,
  getLiteModelSelection,
  getLongDocModelSelection,
  getRoutingModelSelections,
  getSafetyFallbackModelSelection,
  getVisionFallbackModelSelection,
} from './modelSelection';

export const resolveEffectiveAgentId = (
  actionMode: ActionMode,
  agentConfig: AgentConfig | null,
  _searchDepth?: 'normal' | 'deep',
): string | undefined => {
  if (actionMode === 'fast') {
    return 'builtin-fast-search';
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
  turnCapabilityTelemetry?: TurnCapabilityTerminalTelemetry,
): Promise<Response> => {
  const { fetchRawWebpage, mcpConfigs, systemInstructions, enableMemory } = useConfigStore.getState();
  const { chatId, abortController, actionMode, searchDepth, agentConfig, currentBuiltinTools } = state;
  if (!chatId) {
    throw new Error('chatId is required to create a message request');
  }

  const isAgentMode = actionMode === 'agent';
  const isStreamingMode = actionMode === 'agent' || actionMode === 'fast';

  const normalizedMCPConfigs = normalizeMCPServiceConfigs(mcpConfigs);
  const enabledMCPConfigs = agentConfig
    ? normalizedMCPConfigs.filter((mcp) => agentConfig.selectedMcpNames.includes(mcp.name))
    : [];

  const { user } = useAuthStore.getState();
  const userId = user?.id;

  const userInstructions = buildClientInstructions(isAgentMode, agentConfig, systemInstructions, userId);
  const effectiveAgentId = resolveEffectiveAgentId(actionMode, agentConfig, searchDepth);

  const liteModelSelection = getLiteModelSelection();
  const fallbackModelSelection = getFallbackModelSelection(actionMode, agentConfig);
  const safetyFallbackModelSelection = getSafetyFallbackModelSelection(actionMode, agentConfig);
  const fallbackLiteModelSelection = getFallbackLiteModelSelection();
  const {
    light: lightModelSelection,
    fallbackLight: fallbackLightModelSelection,
    reasoning: reasoningModelSelection,
    fallbackReasoning: fallbackReasoningModelSelection,
  } = getRoutingModelSelections(actionMode, agentConfig);
  const visionFallbackModelSelection = getVisionFallbackModelSelection();
  const codeModelSelection = getCodeModelSelection();
  const fallbackCodeModelSelection = getFallbackCodeModelSelection();
  const longDocModelSelection = getLongDocModelSelection();
  const fallbackLongDocModelSelection = getFallbackLongDocModelSelection();

  const query = await buildMultimodalQuery(input, state.files, state.visionFrames);

  // Prioritize locale from personalSettings, fallback to cookie
  const configStore = useConfigStore.getState();
  const savedLocale = configStore.personalSettings?.locale;
  const cookieLocale = getClientLocale();
  const userLocale = normalizeLocaleForBackend(savedLocale || cookieLocale);
  const reasoningDisplayMode =
    configStore.personalSettings?.reasoningDisplayMode ?? configStore.reasoningDisplayMode ?? 'collapsed';

  const migrationBoundProjectId = peekMigrationBoundProjectId();
  const kanbanProjectScope = resolveKanbanProjectScope(migrationBoundProjectId);
  const kanbanDefaultBoardId = resolveKanbanDefaultBoardIdForRequest(currentBuiltinTools, kanbanProjectScope);
  const migrationReadinessAnchor = effectiveAgentId ? consumeMigrationReadinessAnchorForAgent(effectiveAgentId) : null;

  const activeMoaPresetId = useChatStore.getState().activeMoaPresetId;
  const pendingWorkflowTemplateId = useChatStore.getState().pendingWorkflowTemplateId;
  const pendingWorkflowTemplateArgs = useChatStore.getState().pendingWorkflowTemplateArgs;
  const useWorkflowLane = state.isWorkflowMode || Boolean(pendingWorkflowTemplateId);

  const privacyRoutingRequest =
    isStreamingMode && useConfigStore.getState().privacyEnabled
      ? await buildPrivacyRoutingRequest(useConfigStore.getState().privacyRouting)
      : undefined;

  const requestBody = {
    query,
    message_id: messageId,
    chat_id: chatId,
    action_mode: actionMode,
    ...(actionMode === 'fast' && searchDepth && { search_depth: searchDepth }),
    ...(useWorkflowLane && { use_workflow: true }),
    ...(pendingWorkflowTemplateId && { workflow_template_id: pendingWorkflowTemplateId }),
    ...(pendingWorkflowTemplateArgs &&
      Object.keys(pendingWorkflowTemplateArgs).length > 0 && {
        workflow_template_args: pendingWorkflowTemplateArgs,
      }),
    ...(resumeValue !== undefined && { resume_value: resumeValue }),
    ...(archiveRestoreActions && archiveRestoreActions.length > 0
      ? {
          archive_restore_actions: archiveRestoreActions.map((action) => ({
            type: action.type,
            restore_arg: action.restoreArg,
          })),
        }
      : {}),
    ...(turnCapabilityTelemetry && {
      turn_capability_telemetry: {
        source: turnCapabilityTelemetry.source,
        effective_skill_count: turnCapabilityTelemetry.effectiveSkillCount,
        effective_mcp_count: turnCapabilityTelemetry.effectiveMcpCount,
      },
    }),
    ...(modelSelection && { model_selection: modelSelection }),
    timezone: configStore.timezone || getBrowserTimezone(),
    timestamp: getCurrentTimestamp(),
    ...(userLocale && { locale: userLocale }),
    reasoning_display_mode: reasoningDisplayMode,
    ...(effectiveAgentId && { agent_id: effectiveAgentId }),
    ...(migrationReadinessAnchor && {
      migration_readiness_anchor: {
        import_batch_id: migrationReadinessAnchor.importBatchId,
        readiness_status: migrationReadinessAnchor.readinessStatus,
      },
    }),
    ...(migrationBoundProjectId && { migration_bound_project_id: migrationBoundProjectId }),
    ...(useChatStore.getState().workspaceDir && { workspace_dir: useChatStore.getState().workspaceDir }),
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
    ...(codeModelSelection && { code_model_selection: codeModelSelection }),
    ...(fallbackCodeModelSelection && { fallback_code_model_selection: fallbackCodeModelSelection }),
    ...(longDocModelSelection && { long_doc_model_selection: longDocModelSelection }),
    ...(fallbackLongDocModelSelection && { fallback_long_doc_model_selection: fallbackLongDocModelSelection }),
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
        // The saved prompt is read by the server; only a rewrite made in this chat travels with the request.
        ...(agentConfig?.systemPromptEdited && { system_prompt: agentConfig.systemPrompt }),
        skill_configs: agentConfig?.skillConfigs,
        enabled_builtin_tools: currentBuiltinTools,
        browser_source: agentConfig?.browserSource,
        dialog_policy: agentConfig?.dialogPolicy,
        session_recording: agentConfig?.sessionRecording,
        auto_restore_domains: agentConfig?.autoRestoreDomains ?? [],
        orchestration_mode: state.isWorkflowMode ? 'orchestrated' : (agentConfig?.orchestrationMode ?? 'standard'),
        ...(kanbanDefaultBoardId && { kanban_default_board_id: kanbanDefaultBoardId }),
      },
    }),
    ...(isAgentMode &&
      activeMoaPresetId && {
        active_moa_preset_id: activeMoaPresetId,
      }),
    ...(isAgentMode &&
      getAutoMoaReasoning(agentConfig) && {
        auto_moa_reasoning: true,
        ...(getAutoMoaPresetId(agentConfig) && {
          auto_moa_preset_id: getAutoMoaPresetId(agentConfig),
        }),
      }),
    ...(isAgentMode &&
      agentConfig?.forceExternalAgent && {
        force_external_agent: agentConfig.forceExternalAgent,
      }),
    ...(isAgentMode && {
      security_preset: useChatStore.getState().securityPreset,
    }),
    ...(state.activeKnowledgeBaseIds?.length > 0 && {
      session_knowledge_base_ids: state.activeKnowledgeBaseIds,
    }),
    ...(isStreamingMode &&
      useConfigStore.getState().privacyEnabled && {
        privacy_enabled: true,
        privacy_s2_action: useConfigStore.getState().privacyS2Action,
        privacy_s3_action: useConfigStore.getState().privacyS3Action,
        ...(privacyRoutingRequest && { privacy_routing: privacyRoutingRequest }),
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
        ...(state.goalBudgetTokens !== null && { max_tokens: state.goalBudgetTokens }),
        ...(state.goalBudgetUsd !== null && { max_usd: state.goalBudgetUsd }),
        ...(state.goalMaxTimeSeconds !== null && { max_time_seconds: state.goalMaxTimeSeconds }),
        ...(state.goalMaxTurns !== null && { max_turns: state.goalMaxTurns }),
        ...(state.goalConvergenceWindow !== null && { convergence_window: state.goalConvergenceWindow }),
        ...(state.goalLoopOnPause && { loop_on_pause: true }),
        ...(state.goalCheckpointMode && { checkpoint_mode: 'per_todo' }),
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
    ...buildMentionPayload(state, input),
    ...(() => {
      const fileIds = state.files.map((f) => f.id).filter(Boolean) as string[];
      return fileIds.length > 0 ? { uploaded_file_ids: fileIds } : {};
    })(),
    ...(() => {
      const scopedTarget = useScopedArtifactStore.getState().target;
      if (!scopedTarget) {
        return {};
      }
      return {
        scoped_artifact: {
          artifact_id: scopedTarget.artifactId,
          artifact_name: scopedTarget.artifactName,
          scope_label: scopedTarget.scopeLabel,
          kind: scopedTarget.kind,
          selected_snippet: scopedTarget.selectedSnippet,
        },
      };
    })(),
  };

  state.clearMentionReferences();
  useScopedArtifactStore.getState().clearTarget();

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

  const response = await createAISearchStream(requestBody, abortController || undefined);
  return response;
};
