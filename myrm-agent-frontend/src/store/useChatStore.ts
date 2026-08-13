/**
 * [INPUT]
 * @/store/chat/messageRequest::sendMessage (POS: Chat message request assembly layer)
 * @/store/useWorkspaceStore::useWorkspaceStore (POS: Workspace state manager)
 *
 * [OUTPUT]
 * useChatStore: Global Zustand store for the currently active chat session.
 *
 * [POS]
 * Active chat state manager. Acts as the CPU register in the OS Context Switching Architecture, exclusively serving the currently visible tab.
 */

import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import {
  ChatState,
  Message,
  DEFAULT_ENABLED_BUILTIN_TOOLS,
  type BuiltinToolId,
} from '@/store/chat/types';
export type { Message, File, ProgressItem, ChatHistoryItem, PaginationInfo, AgentConfig } from '@/store/chat/types';
import { normalizeArchiveRestoreActions } from './chat/archiveRestoreActions';
import { sendMessage } from './chat/messageRequest';
import { generateStreamRequestMessageId } from './chat/streamRequestMessageId';
import { loadMessages, loadOlderMessages, initializeChat, autoSaveChat, persistActiveChatNavigationSnapshot, resolveInstantChatSnapshot } from './chat/messageManagement';
import { processSuggestions, findAssistantMessageIndex, removeWaitingForTurnStep } from './chat/messageUtils';
import { disarmYoloForPreset, normalizeSecurityPreset } from './chat/securityPreset';
import useQuoteStore from './useQuoteStore';
import useWorkspaceStore from './useWorkspaceStore';
import {
  getChatHistory,
  cancelAgentRequest,
  cancelActiveChatAgent,
  type ChatItem,
} from '@/services/chat';
import { showI18nToast } from '@/services/i18nToastService';
import { fetchWithTimeout } from '@/lib/api';
import { useProjectStore } from '@/store/useProjectStore';
import {
  clearStoredMoaPresetId,
  persistMoaPresetToServer,
  resolveHydratedMoaPresetId,
  writeStoredMoaPresetId,
} from '@/store/chat/moaPresetStorage';

/**
 * Keep history pagination idempotent when a page overlaps with a prior request.
 * The API normally returns disjoint pages, but retries and concurrent sentinel
 * callbacks can deliver the same chat more than once; React list keys must stay
 * unique even when that happens.
 */
function mergeChatHistoryItems(
  existing: ChatItem[],
  incoming: ChatItem[],
): ChatItem[] {
  const byId = new Map<string, ChatItem>();
  for (const item of [...existing, ...incoming]) {
    if (item.id) {
      byId.set(item.id, item);
    }
  }
  return [...byId.values()];
}

function readStoredBuiltinTools(): BuiltinToolId[] {
  if (typeof window === 'undefined') {
    return [...DEFAULT_ENABLED_BUILTIN_TOOLS];
  }

  const stored = localStorage.getItem('currentBuiltinTools');
  if (!stored) {
    return [...DEFAULT_ENABLED_BUILTIN_TOOLS];
  }

  try {
    const parsed = JSON.parse(stored) as BuiltinToolId[];
    const legacyMinimal: BuiltinToolId[] = ['web_search', 'memory'];
    const isLegacyMinimal =
      parsed.length === legacyMinimal.length && legacyMinimal.every((toolId) => parsed.includes(toolId));
    if (isLegacyMinimal) {
      return [...DEFAULT_ENABLED_BUILTIN_TOOLS];
    }
    return parsed;
  } catch {
    return [...DEFAULT_ENABLED_BUILTIN_TOOLS];
  }
}

/** Release inspector (desktop + browser) "controlling" state after a manual stop. */
async function releaseTurnInspectorControls(): Promise<void> {
  const [{ default: useDesktopInspectorStore }, { default: useBrowserInspectorStore }] = await Promise.all([
    import('@/store/useDesktopInspectorStore'),
    import('@/store/useBrowserInspectorStore'),
  ]);
  useDesktopInspectorStore.getState().releaseTurnEngagement();
  useBrowserInspectorStore.getState().releaseTurnEngagement();
}

/** Restore chat UI preferences from localStorage after hydration (SSR-safe). */
export function hydrateChatPreferencesFromStorage(): void {
  if (typeof window === 'undefined') {
    return;
  }

  const actionMode = localStorage.getItem('actionMode');
  const searchDepth = localStorage.getItem('searchDepth');

  useChatStore.setState({
    actionMode: actionMode === 'fast' || actionMode === 'agent' ? actionMode : useChatStore.getState().actionMode,
    searchDepth:
      searchDepth === 'normal' || searchDepth === 'deep' ? searchDepth : useChatStore.getState().searchDepth,
    currentBuiltinTools: readStoredBuiltinTools(),
  });
}

const mentionReferenceKey = (reference: {
  type: string;
  path?: string;
  fileId?: string;
  url?: string;
  label: string;
  startLine?: number;
  endLine?: number;
}) =>
  `${reference.type}:${reference.path ?? reference.fileId ?? reference.url ?? reference.label}:${reference.startLine ?? ''}:${reference.endLine ?? ''}`;

const useChatStore = create<ChatState>()(
  immer((set, get): ChatState => {
    return {
      // 初始状态
      chatId: undefined,
      newChatCreated: false,
      messages: [],
      compactedSummary: null,
      compactedBeforeId: null,
      contextBranches: [],
      contextPinnedFiles: [],
      contextBranchesLoadError: null,
      contextPinnedFilesLoadError: null,
      lastCompactionMeta: null,
      compactionRefreshNonce: 0,
      workspaceDir: null,
      sessionSkillOverrides: null,
      sessionAccessRoots: [],

      // 分页聊天历史状态
      chatHistoryItems: [],
      chatHistoryPagination: null,
      chatHistoryLoading: false,
      chatHistoryError: null,
      chatHistorySourceFilter: null as string | null,
      chatHistorySearchKeyword: '' as string,
      chatHistoryAvailableSources: [] as string[],
      files: [],
      cameraFrames: [],
      hideAttachList: false,
      hasUsedImagesInCurrentChat: false,
      mentionReferences: [],
      actionMode: 'agent',
      activeMoaPresetId: null as string | null,
      searchDepth: 'normal',
      optimizationMode: 'speed',
      isGoalMode: false,
      isWorkflowMode: false,
      pendingWorkflowTemplateId: null,
      pendingWorkflowTemplateDisplayName: null,
      pendingWorkflowTemplateArgs: null,
      incognitoMode: false,
      sandboxMode: false,
      securityPreset: 'hitl' as const,
      goalBudgetTokens: null,
      goalBudgetUsd: null,
      goalMaxTimeSeconds: null,
      goalMaxTurns: null,
      goalProtectedPaths: null,
      goalLoopOnPause: false,
      goalConvergenceWindow: null,
      goalAcceptanceCriteria: null,
      goalConstraints: null,
      goalCheckpointMode: false,
      // Hydrated from localStorage after mount via hydrateChatPreferencesFromStorage().
      currentBuiltinTools: [...DEFAULT_ENABLED_BUILTIN_TOOLS],
      inputMessage: '',
      pendingExplicitSkillActivation: null,
      pendingArchiveRestoreAction: null,
      pendingArchiveRestoreActions: [],
      pendingGapRetry: null,
      agentConfig: null,
      selectedModels: {
        base: null,
        vision: null,
        reasoning: null,
      },
      hasUserSelectedModel: false,
      loading: false,
      loadingOlder: false,
      hasMoreMessages: false,
      nextCursor: null,
      messageAppeared: false,
      isMessagesLoaded: false,
      notFound: false,
      loadError: false,
      isReady: false,
      _messageUpdateScheduled: false,
      regenerateSiblingGroupId: undefined,
      regenerateInstruction: undefined,
      abortController: null,
      currentSessionMessageId: null,
      isConfigPanelExpanded: true, // 默认展开（聊天首页）
      _autoSaveTimer: null,
      environmentAlerts: new Set<string>(),

      // Subagent 智能提示状态
      subagentPromptVisible: false,
      subagentPromptTimer: null,
      subagentPromptMessageId: null,
      activeSessionAnalyticsId: null,
      activeSessionAnalyticsMessageId: null,
      sessionStatuses: {} as Record<string, string>,

      updateMessages: (updater) => set(updater),

      setActiveSessionAnalyticsId: (id) => set({ activeSessionAnalyticsId: id }),
      setActiveSessionAnalyticsMessageId: (id) => set({ activeSessionAnalyticsMessageId: id }),

      setSessionStatus: (chatId: string, status: string) => {
        set((state) => {
          if (status === 'idle') {
            delete state.sessionStatuses[chatId];
          } else {
            state.sessionStatuses[chatId] = status;
          }
        });
      },
      initSessionStatuses: (statuses: Record<string, string>) => {
        set({ sessionStatuses: statuses });
      },

      // 设置方法
      setChatId: (id) => {
        set({ chatId: id, lastCompactionMeta: null, compactionRefreshNonce: 0, contextBranches: [], contextPinnedFiles: [], contextBranchesLoadError: null, contextPinnedFilesLoadError: null });
        useQuoteStore.getState().clearQuote();
      },
      setNewChatCreated: (created) => set({ newChatCreated: created }),
      setMessages: (updater: (state: ChatState) => void) => set(updater),
      refreshCompactionState: async (chatId, meta) => {
        const { getChatDetail, listContextBranches, getContextPins } = await import('@/services/chat');
        const [detailResult, branchesResult, pinsResult] = await Promise.allSettled([
          getChatDetail(chatId, true),
          listContextBranches(chatId),
          getContextPins(chatId),
        ]);
        set((state) => {
          if (state.chatId !== chatId) {
            return;
          }
          if (detailResult.status === 'fulfilled') {
            state.compactedSummary = detailResult.value.chat.compacted_summary;
            state.compactedBeforeId = detailResult.value.chat.compacted_before_id;
          }
          if (branchesResult.status === 'fulfilled') {
            state.contextBranches = branchesResult.value;
            state.contextBranchesLoadError = null;
          } else {
            state.contextBranchesLoadError = 'load_failed';
          }
          if (pinsResult.status === 'fulfilled') {
            state.contextPinnedFiles = pinsResult.value.files;
            state.contextPinnedFilesLoadError = null;
          } else {
            state.contextPinnedFilesLoadError = 'load_failed';
          }
          if (meta && meta.tokensSaved > 0) {
            state.lastCompactionMeta = {
              tokensSaved: meta.tokensSaved,
              snapshotPath: meta.snapshotPath,
            };
          }
          state.compactionRefreshNonce += 1;
        });
      },
      setCompactedSummary: (summary) => set({ compactedSummary: summary }),
      setContextBranches: (branches) => set({ contextBranches: branches, contextBranchesLoadError: null }),
      setContextPinnedFiles: (files) => set({ contextPinnedFiles: files, contextPinnedFilesLoadError: null }),
      setContextBranchesLoadError: (error) => set({ contextBranchesLoadError: error }),
      setContextPinnedFilesLoadError: (error) => set({ contextPinnedFilesLoadError: error }),
      setCompactedBeforeId: (id) => set({ compactedBeforeId: id }),
      setWorkspaceDir: (dir) => set({ workspaceDir: dir }),
      setSessionAccessRoots: (roots) => set({ sessionAccessRoots: roots }),
      setChatHistoryItems: (items) => set({ chatHistoryItems: items }),
      setChatHistoryPagination: (pagination) => set({ chatHistoryPagination: pagination }),
      setChatHistoryLoading: (loading) => set({ chatHistoryLoading: loading }),
      setFiles: (files) => set({ files }),
      setCameraFrames: (frames) => set({ cameraFrames: frames }),
      setHideAttachList: (hide) => set({ hideAttachList: hide }),
      setHasUsedImagesInCurrentChat: (hasUsed) => set({ hasUsedImagesInCurrentChat: hasUsed }),
      addMentionReference: (reference) =>
        set((state) => ({
          mentionReferences: state.mentionReferences.some(
            (item) => mentionReferenceKey(item) === mentionReferenceKey(reference),
          )
            ? state.mentionReferences
            : [...state.mentionReferences, reference],
        })),
      removeMentionReference: (key) =>
        set((state) => ({
          mentionReferences: state.mentionReferences.filter((item) => mentionReferenceKey(item) !== key),
        })),
      removeMentionReferencesByTypes: (types) =>
        set((state) => ({
          mentionReferences: state.mentionReferences.filter((item) => !types.includes(item.type)),
        })),
      clearMentionReferences: () => set({ mentionReferences: [] }),
      setActionMode: (mode) => {
        if (typeof window !== 'undefined') {
          localStorage.setItem('actionMode', mode);
        }
        const state = get();
        const activeMoaPresetId =
          mode === 'agent'
            ? resolveHydratedMoaPresetId(state.chatId, {
                actionMode: 'agent',
                incognitoMode: state.incognitoMode,
              })
            : null;
        set({
          actionMode: mode,
          activeMoaPresetId,
        });
      },
      setActiveMoaPresetId: (presetId) => {
        const prevPresetId = get().activeMoaPresetId;
        const chatId = get().chatId;
        const incognitoMode = get().incognitoMode;
        const rollback = () => {
          if (!incognitoMode) {
            writeStoredMoaPresetId(chatId, prevPresetId);
          }
          set({ activeMoaPresetId: prevPresetId });
        };
        if (!incognitoMode) {
          writeStoredMoaPresetId(chatId, presetId);
        }
        set({ activeMoaPresetId: presetId });
        if (presetId) {
          if (typeof window !== 'undefined') {
            localStorage.setItem('actionMode', 'agent');
          }
          set({ actionMode: 'agent' });
        }
        if (!incognitoMode && chatId) {
          void persistMoaPresetToServer(chatId, presetId, rollback);
        }
      },
      setSearchDepth: (depth) => {
        if (typeof window !== 'undefined') {
          localStorage.setItem('searchDepth', depth);
        }
        set({ searchDepth: depth });
      },
      setOptimizationMode: (mode) => set({ optimizationMode: mode }),
      setIsGoalMode: (isGoalMode) => set({ isGoalMode }),
      setIsWorkflowMode: (isWorkflowMode) => set({ isWorkflowMode }),
      setPendingWorkflowTemplate: (templateId, args = null, displayName = null) =>
        set({
          pendingWorkflowTemplateId: templateId,
          pendingWorkflowTemplateArgs: args,
          pendingWorkflowTemplateDisplayName: displayName,
        }),
      clearPendingWorkflowTemplate: () =>
        set({
          pendingWorkflowTemplateId: null,
          pendingWorkflowTemplateDisplayName: null,
          pendingWorkflowTemplateArgs: null,
        }),
      setIncognitoMode: (incognitoMode) => set({ incognitoMode }),
      setSessionSkillOverrides: (overrides) => set({ sessionSkillOverrides: overrides }),
      setSandboxMode: (sandboxMode) => set({ sandboxMode }),
      setSecurityPreset: (securityPreset) => set({ securityPreset }),
      setGoalBudgetTokens: (tokens) => set({ goalBudgetTokens: tokens }),
      setGoalBudgetUsd: (usd) => set({ goalBudgetUsd: usd }),
      setGoalMaxTimeSeconds: (seconds) => set({ goalMaxTimeSeconds: seconds }),
      setGoalMaxTurns: (turns) => set({ goalMaxTurns: turns }),
      setGoalProtectedPaths: (paths) => set({ goalProtectedPaths: paths }),
      setGoalLoopOnPause: (loop) => set({ goalLoopOnPause: loop }),
      setGoalConvergenceWindow: (window) => set({ goalConvergenceWindow: window }),
      setGoalAcceptanceCriteria: (criteria) => set({ goalAcceptanceCriteria: criteria }),
      setGoalConstraints: (constraints) => set({ goalConstraints: constraints }),
      setGoalCheckpointMode: (checkpoint) => set({ goalCheckpointMode: checkpoint }),
      toggleBuiltinTool: (toolId) => {
        const current = get().currentBuiltinTools;
        const next = current.includes(toolId) ? current.filter((id) => id !== toolId) : [...current, toolId];
        if (typeof window !== 'undefined') {
          localStorage.setItem('currentBuiltinTools', JSON.stringify(next));
        }
        set({ currentBuiltinTools: next });
      },
      setCurrentBuiltinTools: (tools) => {
        if (typeof window !== 'undefined') {
          localStorage.setItem('currentBuiltinTools', JSON.stringify(tools));
        }
        set({ currentBuiltinTools: tools });
      },
      setInputMessage: (message) => set({ inputMessage: message }),
      setPendingExplicitSkillActivation: (activation) =>
        set({ pendingExplicitSkillActivation: activation }),
      setPendingArchiveRestoreAction: (action) => {
        const actions = action ? normalizeArchiveRestoreActions([action]) : [];
        set({
          pendingArchiveRestoreAction: actions[0] ?? null,
          pendingArchiveRestoreActions: actions,
        });
      },
      setPendingArchiveRestoreActions: (actions) => {
        const normalized = normalizeArchiveRestoreActions(actions);
        set({
          pendingArchiveRestoreAction: normalized[0] ?? null,
          pendingArchiveRestoreActions: normalized,
        });
      },
      setPendingGapRetry: (pending) => set({ pendingGapRetry: pending }),
      clearPendingGapRetry: () => set({ pendingGapRetry: null }),
      setAgentConfig: (config) => {
        if (!config) {
          const chatId = get().chatId;
          clearStoredMoaPresetId(chatId);
          if (chatId && !get().incognitoMode) {
            void persistMoaPresetToServer(chatId, null);
          }
          set({ agentConfig: null, activeMoaPresetId: null, securityPreset: 'hitl' });
          return;
        }
        const prevId = get().agentConfig?.agentId;
        const agentChanged = prevId !== undefined && prevId !== config.agentId;
        const firstBind = prevId === undefined && config.agentId !== undefined;
        const builtinTools = [...(config.enabledBuiltinTools ?? DEFAULT_ENABLED_BUILTIN_TOOLS)];
        const autoRestoreDomains = [...(config.autoRestoreDomains ?? [])];
        if (typeof window !== 'undefined') {
          localStorage.setItem('currentBuiltinTools', JSON.stringify(builtinTools));
        }
        if (agentChanged) {
          const chatId = get().chatId;
          clearStoredMoaPresetId(chatId);
          if (chatId && !get().incognitoMode) {
            void persistMoaPresetToServer(chatId, null);
          }
        }
        const shouldInitPreset = firstBind || agentChanged;
        const sessionPreset = normalizeSecurityPreset(config.defaultSecurityPreset);
        if (shouldInitPreset) {
          disarmYoloForPreset(sessionPreset);
        }
        set({
          agentConfig: {
            ...config,
            selectedSkillIds: config.selectedSkillIds ?? [],
            selectedMcpNames: config.selectedMcpNames ?? [],
            systemPrompt: config.systemPrompt ?? '',
            useGlobalInstruction: config.useGlobalInstruction ?? false,
            enabledBuiltinTools: [...builtinTools],
            autoRestoreDomains: [...autoRestoreDomains],
          },
          currentBuiltinTools: builtinTools,
          ...(agentChanged ? { activeMoaPresetId: null } : {}),
          ...(shouldInitPreset ? { securityPreset: sessionPreset } : {}),
        });
      },
      updateAgentConfig: (partial) => {
        const { agentConfig } = get();
        if (agentConfig) {
          const nextBuiltinTools =
            partial.enabledBuiltinTools !== undefined
              ? [...partial.enabledBuiltinTools]
              : [...(agentConfig.enabledBuiltinTools ?? DEFAULT_ENABLED_BUILTIN_TOOLS)];
          const nextAutoRestoreDomains =
            partial.autoRestoreDomains !== undefined
              ? [...partial.autoRestoreDomains]
              : [...(agentConfig.autoRestoreDomains ?? [])];
          set({
            agentConfig: {
              ...agentConfig,
              ...partial,
              enabledBuiltinTools: nextBuiltinTools,
              autoRestoreDomains: nextAutoRestoreDomains,
            },
          });
        } else {
          const nextBuiltinTools =
            partial.enabledBuiltinTools !== undefined
              ? [...partial.enabledBuiltinTools]
              : [...DEFAULT_ENABLED_BUILTIN_TOOLS];
          const nextAutoRestoreDomains =
            partial.autoRestoreDomains !== undefined ? [...partial.autoRestoreDomains] : [];
          set({
            agentConfig: {
              selectedSkillIds: [],
              skillConfigs: {},
              selectedMcpNames: [],
              systemPrompt: '',
              useGlobalInstruction: true,
              ...partial,
              enabledBuiltinTools: nextBuiltinTools,
              autoRestoreDomains: nextAutoRestoreDomains,
            },
          });
        }
      },
      setSelectedModels: (models) => set({ selectedModels: models, hasUserSelectedModel: true }),
      setLoading: (loading) => set({ loading }),
      setMessageAppeared: (appeared) => set({ messageAppeared: appeared }),
      setIsMessagesLoaded: (loaded) => set({ isMessagesLoaded: loaded }),
      setNotFound: (notFound) => set({ notFound }),
      setLoadError: (loadError) => set({ loadError }),
      setConfigPanelExpanded: (expanded) => set({ isConfigPanelExpanded: expanded }),
      toggleConfigPanel: () => set((state) => ({ isConfigPanelExpanded: !state.isConfigPanelExpanded })),
      addEnvironmentAlert: (category) =>
        set((state) => {
          state.environmentAlerts = new Set(state.environmentAlerts).add(category);
        }),
      clearEnvironmentAlerts: () => set({ environmentAlerts: new Set<string>() }),
      stopMessage: () => {
        const {
          chatId,
          abortController: chatAbortController,
          currentSessionMessageId: chatSessionMessageId,
        } = get();
        if (!chatId) {return;}

        const paneId = useWorkspaceStore.getState().panes.find((p: any) => p.chatId === chatId)?.id;

        if (paneId) {
          const abortController = useWorkspaceStore.getState().getPaneAbortController(paneId);
          const currentSessionMessageId = useWorkspaceStore.getState().getPaneCurrentSessionMessageId(paneId);

          if (abortController) {
            void (async () => {
              if (currentSessionMessageId) {
                try {
                  await cancelAgentRequest(currentSessionMessageId);
                  showI18nToast('agent.mobileCommand.stopTaskSuccess', undefined, { type: 'success' });
                } catch {
                  showI18nToast('agent.mobileCommand.stopTaskFailed', undefined, { type: 'warning' });
                }
              } else {
                try {
                  await cancelActiveChatAgent(chatId);
                  showI18nToast('agent.mobileCommand.stopTaskSuccess', undefined, { type: 'success' });
                } catch {
                  showI18nToast('agent.mobileCommand.stopTaskFailed', undefined, { type: 'warning' });
                }
              }
            })();
            abortController.abort();
            useWorkspaceStore.getState().setPaneAbortController(paneId, null);
            void releaseTurnInspectorControls();
            set((state) => {
              state.loading = false;
              state.abortController = null;
              state.messageAppeared = true;
              if (currentSessionMessageId) {
                state.messages = removeWaitingForTurnStep(state.messages, currentSessionMessageId);
              }
            });
          }
          return;
        }

        if (!chatAbortController) {return;}

        void (async () => {
          try {
            await cancelActiveChatAgent(chatId);
            showI18nToast('agent.mobileCommand.stopTaskSuccess', undefined, { type: 'success' });
          } catch {
            showI18nToast('agent.mobileCommand.stopTaskFailed', undefined, { type: 'warning' });
          }
        })();
        chatAbortController.abort();
        void releaseTurnInspectorControls();
        set((state) => {
          state.loading = false;
          state.abortController = null;
          state.messageAppeared = true;
          if (chatSessionMessageId) {
            state.messages = removeWaitingForTurnStep(state.messages, chatSessionMessageId);
          }
        });
      },
      steerMessage: async (message: string) => {
        const { chatId } = get();
        if (!chatId) {return false;}
        try {
          const { isMobileRemoteSurface, mobileRemotePost } = await import('@/lib/mobileRemote');
          if (isMobileRemoteSurface()) {
            await mobileRemotePost(`/api/v1/agents/chats/${chatId}/steer`, { message });
            return true;
          }
          const res = await fetchWithTimeout(`/agents/chats/${chatId}/steer`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
          });
          return res.ok;
        } catch {
          return false;
        }
      },
      redirectMessage: async (message: string) => {
        const { chatId } = get();
        if (!chatId) {return false;}
        try {
          const { isMobileRemoteSurface, mobileRemotePost } = await import('@/lib/mobileRemote');
          if (isMobileRemoteSurface()) {
            await mobileRemotePost(`/api/v1/agents/chats/${chatId}/redirect`, { message });
            return true;
          }
          const res = await fetchWithTimeout(`/agents/chats/${chatId}/redirect`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message }),
          });
          return res.ok;
        } catch {
          return false;
        }
      },

      // 当前会话messageId管理
      getCurrentSessionMessageId: () => {
        const state = get();
        const paneId = useWorkspaceStore.getState().panes.find((p: any) => p.chatId === state.chatId)?.id;

        let currentId = paneId
          ? useWorkspaceStore.getState().getPaneCurrentSessionMessageId(paneId)
          : state.currentSessionMessageId;

        if (!currentId) {
          currentId = generateStreamRequestMessageId();
          if (paneId) {
            useWorkspaceStore.getState().setPaneCurrentSessionMessageId(paneId, currentId);
          }
          set({ currentSessionMessageId: currentId });
        }
        return currentId;
      },
      allocateNewSessionMessageId: () => {
        const state = get();
        const paneId = useWorkspaceStore.getState().panes.find((p: any) => p.chatId === state.chatId)?.id;
        const newMessageId = generateStreamRequestMessageId();
        if (paneId) {
          useWorkspaceStore.getState().setPaneCurrentSessionMessageId(paneId, newMessageId);
        }
        set({ currentSessionMessageId: newMessageId });
        return newMessageId;
      },
      clearCurrentSessionMessageId: () => {
        const state = get();
        const paneId = useWorkspaceStore.getState().panes.find((p: any) => p.chatId === state.chatId)?.id;
        if (paneId) {
          useWorkspaceStore.getState().setPaneCurrentSessionMessageId(paneId, null);
        }
        set({ currentSessionMessageId: null });
      },

      resetSessionState: () => {
        set({
          messages: [],
          files: [],
          mentionReferences: [],
          compactedSummary: null,
          compactedBeforeId: null,
          contextBranches: [],
          contextPinnedFiles: [],
          contextBranchesLoadError: null,
          contextPinnedFilesLoadError: null,
          sessionSkillOverrides: null,
          sessionAccessRoots: [],
          regenerateSiblingGroupId: undefined,
          regenerateInstruction: undefined,
          pendingArchiveRestoreAction: null,
          pendingArchiveRestoreActions: [],
          pendingGapRetry: null,
          currentSessionMessageId: null,
          subagentPromptVisible: false,
          subagentPromptMessageId: null,
          activeSessionAnalyticsId: null,
        });
      },

      // Subagent 智能提示方法
      setSubagentPromptVisible: (visible) => set({ subagentPromptVisible: visible }),
      clearSubagentPromptTimer: () => {
        const { subagentPromptTimer } = get();
        if (subagentPromptTimer) {
          clearTimeout(subagentPromptTimer);
          set({ subagentPromptTimer: null, subagentPromptMessageId: null });
        }
      },
      triggerSubagentPrompt: (messageId) => {
        // 清除已有计时器
        const { subagentPromptTimer } = get();
        if (subagentPromptTimer) {
          clearTimeout(subagentPromptTimer);
        }

        // 启动5秒倒计时
        const timer = setTimeout(() => {
          set({ subagentPromptVisible: true, subagentPromptTimer: null });
        }, 5000);

        set({
          subagentPromptTimer: timer,
          subagentPromptMessageId: messageId,
          subagentPromptVisible: false,
        });
      },

      getMessageContent: (index) => get().messages[index]?.content,
      getChatHistory: (endIndex) => get().messages.slice(0, endIndex),

      // 加载历史消息
      loadMessages: async (chatId) => {
        const actions = {
          setMessages: (updater: (state: ChatState) => void) => set(updater),
          setLoading: (loading: boolean) => set({ loading }),
          setMessageAppeared: (appeared: boolean) => set({ messageAppeared: appeared }),
          setHideAttachList: (hide: boolean) => set({ hideAttachList: hide }),
          setHasUsedImagesInCurrentChat: (hasUsed: boolean) => set({ hasUsedImagesInCurrentChat: hasUsed }),
          setSelectedModels: (models: { base: string | null; vision: string | null; reasoning: string | null }) =>
            set({ selectedModels: models }),
          setHasUserSelectedModel: (hasSelected: boolean) => set({ hasUserSelectedModel: hasSelected }),
          clearCurrentSessionMessageId: () => set({ currentSessionMessageId: null }),
          clearPendingWorkflowTemplate: () => get().clearPendingWorkflowTemplate(),
          setIsWorkflowMode: (enabled: boolean) => set({ isWorkflowMode: enabled }),
          _processSuggestions: get()._processSuggestions,
          scheduleAutoSave: get().scheduleAutoSave,
          setInputMessage: (message: string) => set({ inputMessage: message }),
        };
        await loadMessages(chatId, actions);
      },

      loadOlderMessages: async () => {
        const actions = {
          setMessages: (updater: (state: ChatState) => void) => set(updater),
          setLoading: (loading: boolean) => set({ loading }),
          setMessageAppeared: (appeared: boolean) => set({ messageAppeared: appeared }),
          setHideAttachList: (hide: boolean) => set({ hideAttachList: hide }),
          setHasUsedImagesInCurrentChat: (hasUsed: boolean) => set({ hasUsedImagesInCurrentChat: hasUsed }),
          setSelectedModels: (models: { base: string | null; vision: string | null; reasoning: string | null }) =>
            set({ selectedModels: models }),
          setHasUserSelectedModel: (hasSelected: boolean) => set({ hasUserSelectedModel: hasSelected }),
          clearCurrentSessionMessageId: () => set({ currentSessionMessageId: null }),
          clearPendingWorkflowTemplate: () => get().clearPendingWorkflowTemplate(),
          setIsWorkflowMode: (enabled: boolean) => set({ isWorkflowMode: enabled }),
          _processSuggestions: get()._processSuggestions,
          scheduleAutoSave: get().scheduleAutoSave,
          setInputMessage: (message: string) => set({ inputMessage: message }),
        };
        await loadOlderMessages(actions);
      },

      // 调度自动保存（防抖）
      scheduleAutoSave: () => {
        const { _autoSaveTimer } = get();

        if (_autoSaveTimer) {
          clearTimeout(_autoSaveTimer);
        }

        const timer = setTimeout(() => {
          const latestState = get();

          // 只要有chatId和消息就保存，不检查loading状态
          // 因为loading状态可能由于连续对话而一直为true
          if (latestState.chatId && latestState.messages.length > 0) {
            autoSaveChat(latestState.chatId!, latestState.messages, latestState.actionMode, latestState.incognitoMode)
              .catch((error) => {
                console.error('autoSaveChat 执行失败:', error);
              })
              .finally(() => {
                set({ _autoSaveTimer: null });
              });
          }
        }, 1000); // 1秒防抖延迟

        set({ _autoSaveTimer: timer });
      },

      _processSuggestions: async (lastMsg: Message) => {
        const { messages } = get();
        await processSuggestions(lastMsg, messages, (messageId, suggestions) => {
          set((state) => {
            const messageIndex = findAssistantMessageIndex(state.messages, messageId);
            if (messageIndex !== -1) {
              state.messages[messageIndex].suggestions = suggestions;
            }
          });
        });
      },

      // 发送消息主函数
      sendMessage: async (
        input,
        messageId,
        errorMessage,
        resumeValue,
        archiveRestoreActions,
        agentConfigOverride,
        shouldRecordWikiQuerySuccess,
        turnCapabilityTelemetry,
      ) => {
        const state = get();
        const streamChatId = state.chatId;
        set({ isConfigPanelExpanded: false, environmentAlerts: new Set<string>() });
        await sendMessage(
          input,
          messageId,
          state,
          {
            setMessages: set,
            setLoading: (loading) => set({ loading }),
            clearActiveStream: () => {
              const currentChatId = get().chatId;
              if (currentChatId === streamChatId) {
                set({ loading: false, abortController: null });
              }
              const paneId = useWorkspaceStore.getState().panes.find(
                (pane) => pane.chatId === streamChatId,
              )?.id;
              if (paneId) {
                useWorkspaceStore.getState().setPaneAbortController(paneId, null);
              }
            },
            setMessageAppeared: (appeared) => set({ messageAppeared: appeared }),
            setHideAttachList: (hide) => set({ hideAttachList: hide }),
            setHasUsedImagesInCurrentChat: (hasUsed) => set({ hasUsedImagesInCurrentChat: hasUsed }),
            setSelectedModels: (models) => set({ selectedModels: models }),
            setHasUserSelectedModel: (hasSelected) => set({ hasUserSelectedModel: hasSelected }),
            clearCurrentSessionMessageId: () => set({ currentSessionMessageId: null }),
            clearPendingWorkflowTemplate: () => get().clearPendingWorkflowTemplate(),
            setIsWorkflowMode: (enabled) => set({ isWorkflowMode: enabled }),
            _processSuggestions: get()._processSuggestions,
            scheduleAutoSave: get().scheduleAutoSave,
            setInputMessage: (message) => set({ inputMessage: message }),
          },
          get().getCurrentSessionMessageId,
          get().allocateNewSessionMessageId,
          resumeValue,
          archiveRestoreActions,
          agentConfigOverride,
          shouldRecordWikiQuerySuccess,
          turnCapabilityTelemetry,
        );
      },

      recoverHitlStream: async (chatId: string) => {
        const normalized = chatId.trim();
        if (!normalized) {
          return { ok: false as const, err: 'empty-chat-id' };
        }
        const actions = {
          setMessages: (updater: (state: ChatState) => void) => set(updater),
          setLoading: (loading: boolean) => set({ loading }),
          setMessageAppeared: (appeared: boolean) => set({ messageAppeared: appeared }),
          setHideAttachList: (hide: boolean) => set({ hideAttachList: hide }),
          setHasUsedImagesInCurrentChat: (hasUsed: boolean) => set({ hasUsedImagesInCurrentChat: hasUsed }),
          setSelectedModels: (models: { base: string | null; vision: string | null; reasoning: string | null }) =>
            set({ selectedModels: models }),
          setHasUserSelectedModel: (hasSelected: boolean) => set({ hasUserSelectedModel: hasSelected }),
          clearCurrentSessionMessageId: () => set({ currentSessionMessageId: null }),
          clearPendingWorkflowTemplate: () => get().clearPendingWorkflowTemplate(),
          setIsWorkflowMode: (enabled: boolean) => set({ isWorkflowMode: enabled }),
          _processSuggestions: get()._processSuggestions,
          scheduleAutoSave: get().scheduleAutoSave,
          setInputMessage: (message: string) => set({ inputMessage: message }),
        };
        const { attachForHitlRecovery } = await import('./chat/messageRequest');
        const recovery = await attachForHitlRecovery(normalized, actions, get);
        return {
          ok: true as const,
          attached: recovery.attached,
          queueLen: recovery.queueLen,
          source: recovery.source,
        };
      },

      // 初始化聊天
      initializeChat: (id, options) => {
        const state = get();

        if (state.chatId && state.chatId !== id) {
          persistActiveChatNavigationSnapshot(state);
        }

        const hasInstantSnapshot = Boolean(id && resolveInstantChatSnapshot(id));

        if (!hasInstantSnapshot) {
          set({
            hasUsedImagesInCurrentChat: false,
            hideAttachList: false,
            hasUserSelectedModel: false,
            files: [],
            mentionReferences: [],
            isConfigPanelExpanded: !id,
            environmentAlerts: new Set<string>(),
            selectedModels: {
              base: null,
              vision: null,
              reasoning: null,
            },
          });
        } else {
          set({
            files: [],
            mentionReferences: [],
            isConfigPanelExpanded: false,
            environmentAlerts: new Set<string>(),
          });
        }
        const actions = {
          setMessages: (updater: (state: ChatState) => void) => set(updater),
          setLoading: (loading: boolean) => set({ loading }),
          setMessageAppeared: (appeared: boolean) => set({ messageAppeared: appeared }),
          setHideAttachList: (hide: boolean) => set({ hideAttachList: hide }),
          setHasUsedImagesInCurrentChat: (hasUsed: boolean) => set({ hasUsedImagesInCurrentChat: hasUsed }),
          setSelectedModels: (models: { base: string | null; vision: string | null; reasoning: string | null }) =>
            set({ selectedModels: models }),
          setHasUserSelectedModel: (hasSelected: boolean) => set({ hasUserSelectedModel: hasSelected }),
          clearCurrentSessionMessageId: () => set({ currentSessionMessageId: null }),
          clearPendingWorkflowTemplate: () => get().clearPendingWorkflowTemplate(),
          setIsWorkflowMode: (enabled: boolean) => set({ isWorkflowMode: enabled }),
          _processSuggestions: get()._processSuggestions,
          scheduleAutoSave: get().scheduleAutoSave,
          setInputMessage: (message: string) => set({ inputMessage: message }),
        };
        initializeChat(id, { messages: state.messages, chatId: state.chatId }, actions, options);
      },

      // 分页聊天历史管理
      loadChatHistory: async (page = 1, pageSize = 20) => {
        const { chatHistoryLoading, chatHistoryItems, chatHistorySourceFilter, chatHistorySearchKeyword } = get();
        if (chatHistoryLoading || chatHistoryItems.length > 0) {
          return;
        }
        set({ chatHistoryLoading: true });
        try {
          const projectFilter = useProjectStore.getState().activeFilter;
          const projectId = projectFilter === undefined ? undefined : projectFilter;
          const kw = chatHistorySearchKeyword.trim() || undefined;
          const response = await getChatHistory(page, pageSize, chatHistorySourceFilter ?? undefined, projectId, kw);
          const updates: Partial<ChatState> = {
            chatHistoryItems: mergeChatHistoryItems([], response.items),
            chatHistoryPagination: response.pagination,
            chatHistoryLoading: false,
          };
          if (!chatHistorySourceFilter) {
            const sources = [...new Set(response.items.map((item) => item.source))].filter(Boolean).sort();
            if (sources.length > 0) {
              updates.chatHistoryAvailableSources = sources;
            }
          }
          set(updates);
        } catch (error) {
          console.error('加载聊天历史失败:', error);
          set({ chatHistoryLoading: false });
        }
      },

      loadMoreChatHistory: async () => {
        const { chatHistoryPagination, chatHistoryItems, chatHistoryLoading, chatHistorySourceFilter, chatHistorySearchKeyword } = get();

        if (chatHistoryLoading || !chatHistoryPagination?.has_next) {
          return;
        }

        set({ chatHistoryLoading: true });
        try {
          const nextPage = chatHistoryPagination.page + 1;
          const projectFilter = useProjectStore.getState().activeFilter;
          const projectId = projectFilter === undefined ? undefined : projectFilter;
          const kw = chatHistorySearchKeyword.trim() || undefined;
          const response = await getChatHistory(
            nextPage,
            chatHistoryPagination.page_size,
            chatHistorySourceFilter ?? undefined,
            projectId,
            kw,
          );

          set({
            chatHistoryItems: mergeChatHistoryItems(chatHistoryItems, response.items),
            chatHistoryPagination: response.pagination,
            chatHistoryLoading: false,
          });
        } catch (error) {
          console.error('加载更多聊天历史失败:', error);
          set({ chatHistoryLoading: false });
        }
      },

      setChatHistorySourceFilter: (source: string | null) => {
        set({
          chatHistorySourceFilter: source,
          chatHistoryItems: [],
          chatHistoryPagination: null,
          chatHistoryLoading: false,
          chatHistoryError: null,
        });
        get().loadChatHistory(1, 20);
      },

      setChatHistorySearchKeyword: (keyword: string) => {
        set({
          chatHistorySearchKeyword: keyword,
          chatHistoryItems: [],
          chatHistoryPagination: null,
          chatHistoryLoading: false,
          chatHistoryError: null,
        });
        get().loadChatHistory(1, 20);
      },

      // ── Pinned Threads ──────────────────────────────────────────

      pinChat: async (chatId: string) => {
        const { pinChat: pinChatApi } = await import('@/services/chat');
        const result = await pinChatApi(chatId);
        const items = get().chatHistoryItems.map((item) =>
          item.id === chatId ? { ...item, isPinned: result.isPinned, pinOrder: result.pinOrder } : item,
        );
        set({ chatHistoryItems: items });
      },

      unpinChat: async (chatId: string) => {
        const { unpinChat: unpinChatApi } = await import('@/services/chat');
        await unpinChatApi(chatId);
        const items = get().chatHistoryItems.map((item) =>
          item.id === chatId ? { ...item, isPinned: false, pinOrder: 0 } : item,
        );
        set({ chatHistoryItems: items });
      },

      reorderPinnedChats: async (orderedIds: string[]) => {
        const reorderItems = orderedIds.map((id, i) => ({ id, pin_order: i + 1 }));
        const prev = get().chatHistoryItems;
        const items = prev.map((item) => {
          const idx = orderedIds.indexOf(item.id);
          if (idx !== -1) {return { ...item, pinOrder: idx + 1 };}
          return item;
        });
        set({ chatHistoryItems: items });
        try {
          const { reorderPinnedChats: reorderApi } = await import('@/services/chat');
          await reorderApi(reorderItems);
        } catch {
          set({ chatHistoryItems: prev });
        }
      },
    };
  }),
);

export default useChatStore;

if (typeof window !== 'undefined') {
  (window as Window & { __myrmChatStore?: typeof useChatStore }).__myrmChatStore = useChatStore;
}
