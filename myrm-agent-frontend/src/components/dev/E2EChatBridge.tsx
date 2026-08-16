'use client';

/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天 Zustand store 的业务分层)
 * - @/store/useProviderStore::useProviderStore (POS: Provider 配置 store)
 * - @/store/chat/messageRequest::getModelSelection (POS: 发送前模型选择解析)
 *
 * [OUTPUT]
 * - E2EChatBridge: localhost dev-only `window.__MYRM_E2E_CHAT__` for CDP Chrome E2E
 * - pinLiteModelForE2e: bind agent chat to defaultModelConfig.liteModel (API E2E parity)
 * - pinBasicModelForE2e: bind desktop E2E to defaultModelConfig.baseModel (mimo SSOT)
 * - isE2eProviderSendReady / waitE2eProviderSendReady: getModelSelection SSOT (lite or base)
 *
 * [POS]
 * App shell dev bridge。在 MessageInput 水合前挂载，供 CDP/MCP E2E 驱动聊天与 Goal 模式（非终端用户功能）。
 */
import { useLayoutEffect } from 'react';
import { flushSync } from 'react-dom';
import { getModelSelection, getLightModelSelection } from '@/store/chat/messageRequest';
import { AgentBusyError, executeStreamWithRetry } from '@/store/chat/streamConsumer';
import useChatStore from '@/store/useChatStore';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';
import useApprovalStore from '@/store/useApprovalStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useProviderStore from '@/store/useProviderStore';
import { useSkillStore } from '@/store/skill';
import useConfigStore from '@/store/useConfigStore';
import { guardSearchServiceConfigured } from '@/store/config/searchService';
import type { SearchServiceConfigItem } from '@/store/config/types';
import type { DefaultModelConfig, ProviderConfig } from '@/store/config/providerTypes';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import useDesktopInspectorStore, {
  selectScopedDesktopViewData,
} from '@/store/useDesktopInspectorStore';
import useBrowserInspectorStore, {
  selectScopedBrowserViewData,
} from '@/store/useBrowserInspectorStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { notifyBackgroundTasksChangedForShellJobFinish } from '@/services/backgroundTasksRefresh';
import type { ActionMode, AgentConfig, BuiltinToolId, GoalStatusPayload, ToolSnapshotItem } from '@/store/chat/types';
import useToolsSnapshotStore from '@/store/useToolsSnapshotStore';
import { useSubagentStore, type SubagentNode } from '@/store/chat/useSubagentStore';
import { markLocalBackendUnreachable } from '@/lib/backend-health';
import { fetchWithTimeout } from '@/lib/api';
import { getApiBaseUrl, resolveE2eApiBase as resolveInjectedE2eApiBase } from '@/lib/deploy-mode';
import { markPlatformUnreachable } from '@/lib/platform-readiness';
import { isModelAvailable } from '@/lib/model-binding';
import { shouldPreserveE2eActionMode, shouldRunPrepareAutomationSend } from '@/components/dev/e2eChatBridgeSendPolicy';
import { buildExplicitSkillWireMessage } from '@/lib/utils/messageUtils';
import { getConfigSyncManager } from '@/services/config/ConfigSyncManager';

function isLocalDevHost(): boolean {
  if (typeof window === 'undefined') {return false;}
  const host = window.location.hostname;
  return host === '127.0.0.1' || host === 'localhost';
}

function prepareAutomationSend(): void {
  const { actionMode, setActionMode } = useChatStore.getState();
  if (actionMode === 'fast' || actionMode === 'deep_research') {
    setActionMode('agent');
  }
}

function resolveE2eApiBase(): string {
  return resolveInjectedE2eApiBase() ?? '';
}

function isE2eProviderSendReady(actionMode: ActionMode, agentConfig: AgentConfig | null): boolean {
  const refreshed = useProviderStore.getState();
  if (!refreshed.isInitialized) {
    return false;
  }
  return getModelSelection(actionMode, agentConfig) !== null;
}

async function waitE2eProviderSendReady(deadlineMs: number, preserveActionMode = false): Promise<void> {
  while (Date.now() < deadlineMs) {
    if (!preserveActionMode) {
      prepareAutomationSend();
    }
    const { actionMode, agentConfig } = useChatStore.getState();
    if (isE2eProviderSendReady(actionMode, agentConfig)) {
      return;
    }
    const refreshed = useProviderStore.getState();
    if (!refreshed.isInitialized) {
      await useProviderStore.getState().initProviders();
    } else {
      await useProviderStore.getState().retryInit();
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error('e2e-send-not-ready-after-provider-init');
}

function extractSearchServiceConfigs(body: unknown): SearchServiceConfigItem[] {
  if (!body || typeof body !== 'object') {
    return [];
  }
  const record = body as { value?: { searchServiceConfigs?: unknown }; searchServiceConfigs?: unknown };
  const root =
    record.value && typeof record.value === 'object' ? record.value : (record as { searchServiceConfigs?: unknown });
  const configs = root.searchServiceConfigs;
  return Array.isArray(configs) ? (configs as SearchServiceConfigItem[]) : [];
}

async function fetchSearchServiceConfigsFromApi(apiBase: string): Promise<SearchServiceConfigItem[]> {
  const normalizedApi = apiBase.replace(/\/+$/, '');
  try {
    const resp = await fetch(`${normalizedApi}/api/v1/config/searchServices`, { cache: 'no-store' });
    if (!resp.ok) {
      return [];
    }
    const body: unknown = await resp.json();
    return extractSearchServiceConfigs(body);
  } catch {
    return [];
  }
}

function clearSearchServicesForE2e(): { ok: boolean; count: number } {
  window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
  useConfigStore.setState({ searchServiceConfigs: [] });
  try {
    getConfigSyncManager().set('searchServices', { searchServiceConfigs: [] });
  } catch {
    /* cache-only mirror when sync manager unavailable */
  }
  return { ok: true, count: 0 };
}

async function hydrateSearchServicesFromE2eApi(): Promise<{ ok: boolean; err?: string; count?: number }> {
  try {
    const e2eApiBase = resolveE2eApiBase();
    if (!e2eApiBase) {
      return { ok: false, err: 'no-e2e-api-base' };
    }
    const blockSearchSync = typeof window !== 'undefined' && window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
    const configs = blockSearchSync ? [] : await fetchSearchServiceConfigsFromApi(e2eApiBase);
    useConfigStore.setState({ searchServiceConfigs: configs });
    return { ok: true, count: configs.length };
  } catch {
    return { ok: false, err: 'empty-search-configs' };
  }
}

async function probePrivateBackendReady(e2eApiBase: string): Promise<boolean> {
  try {
    const health = await fetch(`${e2eApiBase}/api/v1/health`, { cache: 'no-store' });
    if (!health.ok) {
      return false;
    }
    const ready = await fetch(`${e2eApiBase}/api/v1/health/ready`, { cache: 'no-store' });
    if (!ready.ok) {
      return false;
    }
    const body = (await ready.json()) as { checks?: { database?: boolean } };
    return body.checks?.database === true;
  } catch {
    return false;
  }
}

type E2eProviderConfigBody = {
  value?: {
    providers?: ProviderConfig[];
    defaultModelConfig?: DefaultModelConfig;
  };
  providers?: ProviderConfig[];
  defaultModelConfig?: DefaultModelConfig;
};

/**
 * E2E 权威配置读取：直接请求后端 /api/v1/config/providers，
 * 绕开 ConfigSyncManager 会话级缓存，避免测试 seed（PRIVATE runtime
 * 并行复用时 upsert 的 corrupt primary）不被前端感知。
 */
async function fetchE2eProviderConfigBody(): Promise<E2eProviderConfigBody> {
  const apiBase = (resolveE2eApiBase() || getApiBaseUrl()).replace(/\/+$/, '');
  const res = await fetch(`${apiBase}/api/v1/config/providers`, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`e2e-provider-config-fetch-${res.status}`);
  }
  const body = (await res.json()) as E2eProviderConfigBody;
  const value = (body.value ?? body) as E2eProviderConfigBody;
  if (typeof window !== 'undefined' && window.__MYRM_E2E_RUNTIME__) {
    console.log(
      '[E2EChatBridge] authoritative providers base=%s primary=%s/%s count=%d',
      apiBase,
      value.defaultModelConfig?.baseModel?.primary?.providerId ?? '?',
      value.defaultModelConfig?.baseModel?.primary?.model ?? '?',
      value.providers?.length ?? 0,
    );
  }
  return value;
}

type E2eChatSessionOpts = { preserveActionMode?: boolean };

async function initProvidersForE2e(opts?: E2eChatSessionOpts): Promise<void> {
  const e2eApiBase = resolveE2eApiBase();
  if (e2eApiBase) {
    const preserveActionMode = shouldPreserveE2eActionMode(
      useChatStore.getState().actionMode,
      Boolean(opts?.preserveActionMode),
    );
    if (shouldRunPrepareAutomationSend(preserveActionMode)) {
      prepareAutomationSend();
    }
    const { actionMode, agentConfig } = useChatStore.getState();
    if (isE2eProviderSendReady(actionMode, agentConfig)) {
      return;
    }

    markPlatformUnreachable();
    markLocalBackendUnreachable();
    const normalizedApi = e2eApiBase.replace(/\/+$/, '');
    const workspaceStatus = typeof window !== 'undefined' ? window.__MYRM_WORKSPACE_STREAM_STATUS__?.() : undefined;
    const workspaceConnected =
      workspaceStatus?.connected === true && (workspaceStatus.origin ?? '').replace(/\/+$/, '') === normalizedApi;

    const deadline = Date.now() + 120_000;
    let ready = false;
    while (Date.now() < deadline) {
      if (await probePrivateBackendReady(e2eApiBase)) {
        ready = true;
        break;
      }
      if (workspaceConnected) {
        try {
          const health = await fetch(`${normalizedApi}/api/v1/health`, { cache: 'no-store' });
          if (health.ok) {
            ready = true;
            break;
          }
        } catch {
          // retry until deadline
        }
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    if (!ready) {
      throw new Error('e2e-private-backend-not-ready');
    }
    await useProviderStore.getState().retryInit();
    if (typeof window !== 'undefined' && window.__MYRM_E2E_BLOCK_SEARCH_SYNC__) {
      clearSearchServicesForE2e();
    } else {
      await hydrateSearchServicesFromE2eApi();
    }
    await waitE2eProviderSendReady(Date.now() + 120_000, preserveActionMode);
    return;
  }
  const providerState = useProviderStore.getState();
  if (!providerState.isInitialized) {
    await providerState.initProviders();
  }
  const preserveActionMode = shouldPreserveE2eActionMode(useChatStore.getState().actionMode, false);
  await waitE2eProviderSendReady(Date.now() + 120_000, preserveActionMode);
}

type E2eSubmitResult = {
  ok: boolean;
  err?: string;
  chatId?: string | null;
  mode?: string;
  debug?: Record<string, unknown>;
};

type SendTurnProfile = 'live' | 'read';

const E2E_SEND_GENERATION_KEY = '__MYRM_E2E_SEND_GENERATION__';

function readE2eSendGeneration(): number {
  const raw = (window as unknown as Record<string, unknown>)[E2E_SEND_GENERATION_KEY];
  return typeof raw === 'number' && Number.isFinite(raw) ? raw : 0;
}

function bumpE2eSendGeneration(_reason: string): number {
  const next = readE2eSendGeneration() + 1;
  (window as unknown as Record<string, unknown>)[E2E_SEND_GENERATION_KEY] = next;
  return next;
}

const SEND_TURN_REV = 'R72-F';
const SEND_TURN_NO_OP_MS = 3_000;

/** SHPOIB private-backend E2E: user persist + SSE arm can exceed 3s under parallel MUX. */
function resolveSendTurnNoOpMs(): number {
  if (typeof window === 'undefined') {
    return SEND_TURN_NO_OP_MS;
  }
  if (resolveE2eApiBase()) {
    return 12_000;
  }
  return SEND_TURN_NO_OP_MS;
}

function buildSendTurnDiagnostic(chatId: string | null): Record<string, unknown> {
  const processingIds = [...useToolApprovalStore.getState().processingMessageIds];
  return {
    rev: SEND_TURN_REV,
    directSse: Boolean(
      typeof window !== 'undefined' && (window as unknown as Record<string, unknown>).__MYRM_E2E_DIRECT_SSE__,
    ),
    turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? null,
    provider: window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null,
    workspace: window.__MYRM_WORKSPACE_STREAM_STATUS__?.() ?? null,
    multiplex: window.__MYRM_MULTIPLEX_STATS__?.() ?? null,
    chatId,
    processingIds,
    approvalQueueLen: useToolApprovalStore.getState().queue.length,
  };
}

/** Mirror createSmartUpdater routing so OBSERVE reads the same state SUBMIT writes. */
function resolveE2eProgressChatState(chatId: string): {
  messages: Array<{ role?: string }>;
  loading: boolean;
  abortController: AbortController | null;
} {
  const chatState = useChatStore.getState();
  const workspaceState = useWorkspaceStore.getState();
  if (!chatId || workspaceState.panes.length === 0) {
    return {
      messages: chatState.messages,
      loading: chatState.loading,
      abortController: chatState.abortController,
    };
  }
  const activePane = workspaceState.panes.find((pane) => pane.id === workspaceState.activePaneId);
  if (activePane?.chatId === chatId) {
    return {
      messages: chatState.messages,
      loading: chatState.loading,
      abortController: chatState.abortController,
    };
  }
  const pane = workspaceState.panes.find((entry) => entry.chatId === chatId);
  if (pane?.snapshot) {
    return {
      messages: pane.snapshot.messages ?? [],
      loading: Boolean(pane.snapshot.loading),
      abortController: pane.abortController ?? chatState.abortController,
    };
  }
  return {
    messages: chatState.messages,
    loading: chatState.loading,
    abortController: chatState.abortController,
  };
}

function resolveE2eTurnProgress(
  chatId: string,
  baselineUsers: number,
): { userCount: number; streaming: boolean; uiProgress: boolean } {
  const chatState = useChatStore.getState();
  const workspaceState = useWorkspaceStore.getState();
  const progressState = resolveE2eProgressChatState(chatId);
  const pane = workspaceState.panes.find((entry) => entry.chatId === chatId);
  const paneAbort = pane?.id ? workspaceState.getPaneAbortController(pane.id) : null;
  const userCount = progressState.messages.filter((msg) => msg.role === 'user').length;
  const streaming = Boolean(
    progressState.loading ||
    progressState.abortController ||
    paneAbort ||
    chatState.loading ||
    chatState.abortController,
  );
  return {
    userCount,
    streaming,
    uiProgress: userCount > baselineUsers || streaming,
  };
}

async function countApiUserMessages(chatId: string): Promise<number> {
  const messagesUrl = `${getApiBaseUrl().replace(/\/+$/, '')}/chats/${encodeURIComponent(chatId)}/messages`;
  try {
    const resp = await fetch(messagesUrl, { cache: 'no-store' });
    if (!resp.ok) {
      return 0;
    }
    const payload = (await resp.json()) as {
      data?: { messages?: Array<{ role?: string }> };
    };
    return payload.data?.messages?.filter((entry) => entry.role === 'user').length ?? 0;
  } catch {
    return 0;
  }
}

async function submitAndObserveTurn(
  message: string,
  baselineUsers: number,
  profile: SendTurnProfile,
  preserveActionMode = false,
  ephemeralSubagents?: Record<string, unknown>,
): Promise<E2eSubmitResult> {
  const trimmed = message.trim();
  if (!trimmed) {
    return { ok: false, err: 'empty-message', mode: 'sendTurnEmpty' };
  }
  const startGen = readE2eSendGeneration();
  try {
    window.__MYRM_E2E_CHAT__?.abortActiveStream?.();
    window.__MYRM_E2E_CHAT__?.releaseActiveStreamForApiResume?.();
    const { actionMode: sendActionMode } = useChatStore.getState();
    const shouldPreserveActionMode = shouldPreserveE2eActionMode(sendActionMode, preserveActionMode);
    const sessionOpts = shouldPreserveActionMode ? { preserveActionMode: true } : undefined;
    await window.__MYRM_E2E_CHAT__?.ensureChatSession?.(sessionOpts);
    flushSync(() => {
      useChatStore.getState().setInputMessage(trimmed);
    });
    const chatIdBeforeSend = useChatStore.getState().chatId?.trim() || '';
    if (!chatIdBeforeSend) {
      return { ok: false, err: 'no-chat-id', mode: 'sendTurnNoChatId' };
    }
    const { actionMode: currentActionMode } = useChatStore.getState();
    if (currentActionMode === 'fast' || currentActionMode === 'deep_research') {
      const configs = useConfigStore.getState().searchServiceConfigs;
      if (!guardSearchServiceConfigured(configs)) {
        return {
          ok: false,
          err: 'search-not-configured',
          mode: 'sendTurnSearchGuard',
          debug: {
            actionMode: currentActionMode,
            searchCount: configs.length,
            enabledCount: configs.filter((item) => item.enabled).length,
          },
        };
      }
    }
    const e2eApiBase = resolveE2eApiBase();
    if (e2eApiBase) {
      const win = window as unknown as Record<string, unknown>;
      // Dual-Plane gap chrome_e2e tests pin false before send to capture SSE via mux.
      if (win.__MYRM_E2E_DIRECT_SSE__ !== false) {
        win.__MYRM_E2E_DIRECT_SSE__ = true;
      }
    }
    if (
      e2eApiBase &&
      !(window as unknown as Record<string, unknown>).__MYRM_E2E_DIRECT_SSE__ &&
      typeof window.__MYRM_WAIT_WORKSPACE_STREAM__ === 'function'
    ) {
      const workspaceReady = await window.__MYRM_WAIT_WORKSPACE_STREAM__(30_000);
      if (!workspaceReady?.ok) {
        return {
          ok: false,
          err: workspaceReady?.err ?? 'workspace-stream-not-ready',
          mode: 'sendTurnWorkspaceNotReady',
          chatId: chatIdBeforeSend,
          debug: {
            phase: 'ARM',
            workspace: window.__MYRM_WORKSPACE_STREAM_STATUS__?.() ?? null,
            apiBase: getApiBaseUrl(),
            sendGeneration: startGen,
          },
        };
      }
    }
    if (!window.__MYRM_E2E_CHAT__?.isSendReady?.()) {
      return {
        ok: false,
        err: 'send-not-ready',
        mode: 'sendTurnNotReady',
        debug: window.__MYRM_E2E_CHAT__?.debugProviderState?.(),
      };
    }
    const staleRequestId = useChatStore.getState().currentSessionMessageId;
    if (staleRequestId) {
      useToolApprovalStore.getState().unmarkProcessing(staleRequestId);
    }
    useChatStore.getState().clearCurrentSessionMessageId();
    const messagesLoadedDeadline = Date.now() + 30_000;
    while (Date.now() < messagesLoadedDeadline) {
      const loadedState = useChatStore.getState();
      if (loadedState.isMessagesLoaded && !loadedState.loading) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    const sendReadyDeadline = Date.now() + 30_000;
    while (Date.now() < sendReadyDeadline) {
      const chatState = useChatStore.getState();
      if (!chatState.loading && !chatState.abortController) {
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    const preSendState = useChatStore.getState();
    if (preSendState.loading || preSendState.abortController) {
      return {
        ok: false,
        err: 'chat-still-busy',
        mode: 'sendTurnBusy',
        debug: {
          turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.(),
          ...window.__MYRM_E2E_CHAT__?.debugProviderState?.(),
        },
      };
    }
    if (shouldRunPrepareAutomationSend(shouldPreserveActionMode)) {
      prepareAutomationSend();
    }
    useToolApprovalStore.getState().clearAll();
    let agentConfigOverride: AgentConfig | undefined;
    if (ephemeralSubagents && Object.keys(ephemeralSubagents).length > 0) {
      // JIT delegation is an agent-mode flow: the backend drops ephemeral_subagents
      // when action_mode=fast (converter.py sets jit_subagents=None for fast search).
      // Chrome E2E profile can persist actionMode=fast in localStorage, so force agent.
      if (!preserveActionMode) {
        useChatStore.getState().setActionMode('agent');
      }
      // 不依赖 store.agentConfig 的稳定性：直接通过 sendMessage 的
      // agentConfigOverride 参数注入，requestState 在入口即固定，payload
      // 一定携带 ephemeral_subagents（store 后续被 attach 重置也不受影响）。
      const currentConfig = useChatStore.getState().agentConfig;
      agentConfigOverride = {
        ...((currentConfig ?? {}) as Partial<AgentConfig>),
        ephemeralSubagents,
      } as AgentConfig;
      window.__MYRM_E2E_EPH_APPLIED__ = {
        keys: Object.keys(ephemeralSubagents),
        at: Date.now(),
        forced: !currentConfig,
      };
    }
    const { actionMode } = useChatStore.getState();
    const agentConfig = agentConfigOverride ?? useChatStore.getState().agentConfig;
    if (!getModelSelection(actionMode, agentConfig)) {
      return {
        ok: false,
        err: 'model-selection-unavailable',
        mode: 'sendTurnValidateFailed',
        chatId: chatIdBeforeSend,
        debug: { phase: 'ARM', ...buildSendTurnDiagnostic(chatIdBeforeSend), baselineUsers },
      };
    }
    let submitError: string | null = null;
    let sendSettledEmpty = false;
    const kickoffAt = Date.now();
    const sendPromise = useChatStore.getState().sendMessage(
      trimmed,
      undefined,
      undefined,
      undefined,
      undefined,
      agentConfigOverride,
    );
    await Promise.resolve();
    void sendPromise
      .then(() => {
        const chatId = useChatStore.getState().chatId?.trim() || chatIdBeforeSend;
        const progress = resolveE2eTurnProgress(chatId, baselineUsers);
        if (!progress.uiProgress) {
          sendSettledEmpty = true;
        }
      })
      .catch((error) => {
        submitError = error instanceof Error ? error.message : String(error);
      });
    const observeDeadline = Date.now() + 45_000;
    while (Date.now() < observeDeadline) {
      if (submitError) {
        return {
          ok: false,
          err: submitError,
          mode: 'sendTurnSubmitError',
          chatId: chatIdBeforeSend,
          debug: { phase: 'SUBMIT', sendGeneration: startGen, ...buildSendTurnDiagnostic(chatIdBeforeSend) },
        };
      }
      if (readE2eSendGeneration() !== startGen) {
        return {
          ok: false,
          err: 'session-reset-during-submit',
          mode: 'sendTurnGenerationMismatch',
          chatId: chatIdBeforeSend,
          debug: { phase: 'OBSERVE', sendGeneration: startGen, currentGeneration: readE2eSendGeneration() },
        };
      }
      const chatState = useChatStore.getState();
      const chatId = chatState.chatId?.trim() || '';
      if (!chatId) {
        await new Promise((resolve) => setTimeout(resolve, 250));
        continue;
      }
      const { userCount, streaming, uiProgress } = resolveE2eTurnProgress(chatId, baselineUsers);
      const elapsedMs = Date.now() - kickoffAt;
      if (sendSettledEmpty && elapsedMs >= 1_500) {
        const apiUsersProbe = await countApiUserMessages(chatId);
        return {
          ok: false,
          err: 'send-message-settled-without-progress',
          mode: 'sendTurnSubmitNoOp',
          chatId,
          debug: {
            phase: 'SUBMIT',
            profile,
            sendGeneration: startGen,
            apiUsers: apiUsersProbe,
            userCount,
            streaming,
            baselineUsers,
            elapsedMs,
            ...buildSendTurnDiagnostic(chatId),
          },
        };
      }
      if (elapsedMs >= resolveSendTurnNoOpMs() && !uiProgress) {
        const apiUsersProbe = await countApiUserMessages(chatId);
        if (apiUsersProbe <= baselineUsers) {
          return {
            ok: false,
            err: 'send-kickoff-no-progress',
            mode: 'sendTurnSubmitNoOp',
            chatId,
            debug: {
              phase: 'OBSERVE',
              profile,
              sendGeneration: startGen,
              apiUsers: apiUsersProbe,
              userCount,
              streaming,
              baselineUsers,
              elapsedMs,
              sendSettledEmpty,
              ...buildSendTurnDiagnostic(chatId),
            },
          };
        }
      }
      const apiUsers = await countApiUserMessages(chatId);
      const apiOk = apiUsers > baselineUsers;
      // A local placeholder/stream can be produced before the private backend
      // accepts the POST. It is not an admission signal: sealing here would
      // let the E2E flow continue while the API still has no user row. Every
      // live turn must therefore have both UI progress and an API-side row.
      const liveOk = apiOk && uiProgress;
      const readOk = apiOk && uiProgress;
      if ((profile === 'live' && liveOk) || (profile === 'read' && readOk)) {
        // store.agentConfig may have been reset by attach after POST; the payload
        // itself is guaranteed by agentConfigOverride, so reflect that in diagnostics.
        const ephKeys = window.__MYRM_E2E_EPH_APPLIED__?.keys ?? [];
        return {
          ok: true,
          chatId,
          mode: 'sendTurnSealed',
          debug: {
            phase: 'SEAL',
            profile,
            rev: SEND_TURN_REV,
            sendGeneration: startGen,
            apiUsers,
            userCount,
            streaming,
            baselineUsers,
            chatIdBeforeSend: chatIdBeforeSend !== chatId ? chatIdBeforeSend : undefined,
            ephKeys,
            actionModeAtSeal: useChatStore.getState().actionMode,
          },
        };
      }
      await new Promise((resolve) => setTimeout(resolve, 250));
    }
    const finalState = useChatStore.getState();
    const finalChatId = finalState.chatId?.trim() || chatIdBeforeSend;
    const finalProgress = finalChatId
      ? resolveE2eTurnProgress(finalChatId, baselineUsers)
      : { userCount: 0, streaming: false, uiProgress: false };
    const finalApiUsers = finalChatId ? await countApiUserMessages(finalChatId) : 0;
    return {
      ok: false,
      err: 'send-turn-observe-timeout',
      mode: 'sendTurnObserveTimeout',
      chatId: finalChatId,
      debug: {
        phase: 'OBSERVE',
        profile,
        rev: SEND_TURN_REV,
        sendGeneration: startGen,
        apiUsers: finalApiUsers,
        userCount: finalProgress.userCount,
        streaming: finalProgress.streaming,
        baselineUsers,
        sendSettledEmpty,
        ...buildSendTurnDiagnostic(finalChatId || chatIdBeforeSend),
      },
    };
  } catch (error) {
    return {
      ok: false,
      err: error instanceof Error ? error.message : String(error),
      mode: 'sendTurnUnexpected',
      debug: { phase: 'SUBMIT', sendGeneration: startGen },
    };
  }
}

export type SseEventRecorder = (
  type: string,
  messageId?: string | null,
  data?: unknown,
) => void;

export default function E2EChatBridge() {
  useLayoutEffect(() => {
    if (!isLocalDevHost()) {return;}

    const sseEvents: Array<{ type: string; messageId: string | null; data?: unknown }> = [];
    let sseCaptureMessageId: string | null = null;
    let sseCaptureLocked = false;
    (
      window as Window & { __MYRM_E2E_RECORD_SSE__?: SseEventRecorder }
    ).__MYRM_E2E_RECORD_SSE__ = (type: string, messageId?: string | null, data?: unknown) => {
      if (sseCaptureLocked) {
        const normalizedId = typeof messageId === 'string' && messageId.trim() ? messageId.trim() : null;
        if (type !== 'capability_gap' || !normalizedId) {
          return;
        }
        sseCaptureMessageId = normalizedId;
        sseCaptureLocked = false;
      }
      const normalizedId = typeof messageId === 'string' && messageId.trim() ? messageId.trim() : null;
      if (sseCaptureMessageId && normalizedId !== sseCaptureMessageId) {
        return;
      }
      sseEvents.push({
        type,
        messageId: normalizedId,
        data,
      });
      if (sseEvents.length > 64) {
        sseEvents.splice(0, sseEvents.length - 64);
      }
    };

    (window as unknown as Record<string, unknown>).__MYRM_E2E_SEND_TURN_REV__ = SEND_TURN_REV;

    window.__MYRM_E2E_CHAT__ = {
      __e2eFallback: false,
      sendTurnRev: () => SEND_TURN_REV,
      ensureProviders: initProvidersForE2e,
      prepareAutomationSend,
      isProvidersInitialized: () => useProviderStore.getState().isInitialized,
      isSendReady: () => {
        if (!useProviderStore.getState().isInitialized) {
          return false;
        }
        const { actionMode, agentConfig } = useChatStore.getState();
        return getModelSelection(actionMode, agentConfig) !== null;
      },
      setWorkflowMode: (enabled: boolean) => {
        useChatStore.getState().setIsWorkflowMode(enabled);
      },
      isWorkflowMode: () => useChatStore.getState().isWorkflowMode,
      getLastAssistantMessageId: () => {
        const assistants = useChatStore.getState().messages.filter((message) => message.role === 'assistant');
        return assistants[assistants.length - 1]?.messageId ?? null;
      },
      sendWorkflowTemplateRun: async (templateId: string, query: string, displayName?: string) => {
        const { submitWorkflowTemplateRun } = await import('@/lib/workflow/submitWorkflowTemplateRun');
        return submitWorkflowTemplateRun({
          templateId,
          query,
          displayName,
        });
      },
      syncSearchServicesFromE2eApi: hydrateSearchServicesFromE2eApi,
      clearSearchServicesForE2e,
      debugSearchState: () => {
        const configs = useConfigStore.getState().searchServiceConfigs;
        const enabled = configs.filter((item) => item.enabled);
        return {
          count: configs.length,
          enabledCount: enabled.length,
          blockSearchSync: Boolean(window.__MYRM_E2E_BLOCK_SEARCH_SYNC__),
        };
      },
      debugSecurityState: () => {
        const syncManager = getConfigSyncManager();
        const securityConfig = syncManager.get('securityConfig');
        const { securityPreset, agentConfig } = useChatStore.getState();
        return {
          securityPreset,
          boundAgentId: agentConfig?.agentId ?? null,
          yoloModeEnabled: securityConfig?.yoloModeEnabled ?? null,
          configInitialized: syncManager.isInitialized,
          hasSecurityConfig: securityConfig != null,
        };
      },
      debugProviderState: () => {
        const { isInitialized, providers, defaultModelConfig } = useProviderStore.getState();
        const { actionMode, agentConfig, chatId, currentSessionMessageId } = useChatStore.getState();
        const selection = getModelSelection(actionMode, agentConfig);
        const lightSelection = getLightModelSelection(agentConfig);
        return {
          isInitialized,
          actionMode,
          chatId,
          streamRequestMessageId: currentSessionMessageId?.trim() || null,
          providerIds: providers.map((p) => p.id),
          enabledProviderIds: providers.filter((p) => p.isEnabled).map((p) => p.id),
          primary: defaultModelConfig?.baseModel?.primary ?? null,
          agentModelSelection: agentConfig?.modelSelection ?? null,
          selection: selection ? { providerId: selection.providerId, model: selection.model } : null,
          routing: {
            agentHasRouting: Boolean(agentConfig?.routingConfig),
            agentRoutingEnabled: agentConfig?.routingConfig?.enabled ?? null,
            dmcHasRouting: Boolean(defaultModelConfig?.routingConfig),
            dmcRoutingEnabled: defaultModelConfig?.routingConfig?.enabled ?? null,
            dmcLightPrimary: defaultModelConfig?.routingConfig?.lightModel?.primary ?? null,
            lightSelection: lightSelection
              ? { providerId: lightSelection.providerId, model: lightSelection.model }
              : null,
          },
        };
      },
      ensureChatSession: async (opts?: E2eChatSessionOpts) => {
        await initProvidersForE2e(opts);
        const preserveActionMode = shouldPreserveE2eActionMode(
          useChatStore.getState().actionMode,
          Boolean(opts?.preserveActionMode),
        );
        if (shouldRunPrepareAutomationSend(preserveActionMode)) {
          prepareAutomationSend();
        }
        if (!useChatStore.getState().chatId?.trim()) {
          flushSync(() => {
            useChatStore.getState().initializeChat(undefined);
          });
        }
      },
      attachToChat: async (chatId: string) => {
        const id = chatId.trim();
        if (!id) {
          throw new Error('empty-chat-id');
        }
        await initProvidersForE2e();
        if (typeof window.__MYRM_E2E_RUNTIME_READY__ !== 'undefined') {
          await window.__MYRM_E2E_RUNTIME_READY__;
        }
        prepareAutomationSend();
        flushSync(() => {
          const state = useChatStore.getState();
          const needsForcedReload =
            state.chatId === id && (state.notFound || state.loadError || !state.isMessagesLoaded || state.loading);
          if (needsForcedReload) {
            useChatStore.setState({
              notFound: false,
              loadError: false,
              isMessagesLoaded: false,
              loading: false,
            });
          }
          useChatStore.getState().initializeChat(id, { forceReload: needsForcedReload });
        });
        const configuredAttachMs = Number(window.__MYRM_E2E_ATTACH_TIMEOUT_MS__);
        const attachMs =
          Number.isFinite(configuredAttachMs) && configuredAttachMs >= 60_000 ? configuredAttachMs : 90_000;
        const deadline = Date.now() + attachMs;
        while (Date.now() < deadline) {
          const state = useChatStore.getState();
          if (state.chatId === id && state.isMessagesLoaded && !state.notFound && !state.loadError && !state.loading) {
            flushSync(() => {
              useChatStore.setState({
                messages: [...state.messages],
                isMessagesLoaded: true,
                loading: false,
                messageAppeared: true,
              });
            });
            window.dispatchEvent(new CustomEvent('myrm-e2e-chat-route-hydrated', { detail: { chatId: id } }));
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, 200));
        }
        const finalState = useChatStore.getState();
        if (
          finalState.chatId === id &&
          finalState.isMessagesLoaded &&
          !finalState.notFound &&
          !finalState.loadError &&
          !finalState.loading
        ) {
          window.dispatchEvent(new CustomEvent('myrm-e2e-chat-route-hydrated', { detail: { chatId: id } }));
          return;
        }
        throw new Error(
          `attach-timeout chatId=${finalState.chatId} notFound=${finalState.notFound} loadError=${finalState.loadError} loaded=${finalState.isMessagesLoaded}`,
        );
      },
      pokeChatRouteRender: (chatId: string) => {
        const id = chatId.trim();
        if (!id) {
          return { ok: false, err: 'empty-chat-id' };
        }
        flushSync(() => {
          const state = useChatStore.getState();
          useChatStore.setState({
            chatId: id,
            isMessagesLoaded: true,
            loading: false,
            messageAppeared: true,
            notFound: false,
            loadError: false,
            messages: Array.isArray(state.messages) ? [...state.messages] : [],
          });
        });
        window.dispatchEvent(new CustomEvent('myrm-e2e-chat-route-hydrated', { detail: { chatId: id } }));
        const next = useChatStore.getState();
        const routeReady =
          next.chatId === id &&
          next.isMessagesLoaded &&
          (next.messages.length > 0 || Boolean(next.compactedSummary?.trim()));
        return {
          ok: true,
          routeReady,
          msgCount: next.messages.length,
          hasSkeleton: Boolean(
            typeof document !== 'undefined' && document.querySelector('[data-testid="message-list-skeleton"]'),
          ),
        };
      },
      recoverHitlStream: async (chatId: string) => {
        const id = chatId.trim();
        if (!id) {
          return { ok: false, err: 'empty-chat-id' };
        }
        if (typeof window.__MYRM_E2E_RUNTIME_READY__ !== 'undefined') {
          await window.__MYRM_E2E_RUNTIME_READY__;
        }
        return useChatStore.getState().recoverHitlStream(id);
      },
      resetChat: () => {
        bumpE2eSendGeneration('resetChat');
        flushSync(() => {
          const { actionMode } = useChatStore.getState();
          if (!shouldPreserveE2eActionMode(actionMode)) {
            prepareAutomationSend();
          }
          useChatStore.getState().initializeChat(undefined);
        });
      },
      setInputMessage: (message: string) => {
        flushSync(() => {
          useChatStore.getState().setInputMessage(message);
        });
      },
      submitSteerNudge: async (message: string) => {
        const trimmed = message.trim();
        if (!trimmed) {
          return { ok: false, err: 'empty-message' };
        }
        flushSync(() => {
          useChatStore.getState().setInputMessage(trimmed);
        });
        const storeOk = await useChatStore.getState().steerMessage(trimmed);
        if (storeOk) {
          flushSync(() => {
            useChatStore.getState().setInputMessage('');
          });
          return { ok: true, mode: 'steerStore' };
        }
        const buttons = [...document.querySelectorAll('button[aria-label]')];
        const steerBtn = buttons.find((btn) => {
          const label = String(btn.getAttribute('aria-label') || '').toLowerCase();
          return (
            label.includes('steer') || label.includes('guidance') || label.includes('转向') || label.includes('指导')
          );
        }) as HTMLButtonElement | undefined;
        if (steerBtn && !steerBtn.disabled) {
          steerBtn.click();
          return { ok: true, mode: 'steerClick' };
        }
        const baselineUsers = window.__MYRM_E2E_CHAT__?.turnSnapshot?.().userCount ?? 0;
        const result = await submitAndObserveTurn(trimmed, baselineUsers, 'live');
        return result.ok
          ? { ok: true, mode: 'steerSendFallback', detail: result }
          : { ok: false, err: 'steer-fallback-send-failed', detail: result };
      },
      clearStreamRequestMessageId: () => {
        useChatStore.getState().clearCurrentSessionMessageId();
      },
      sendChatMessage: async (
        text: string,
        opts?: {
          baselineUserCount?: number;
          waitForStreamCompletion?: boolean;
          preserveActionMode?: boolean;
          profile?: SendTurnProfile;
          ephemeralSubagents?: Record<string, unknown>;
        },
      ): Promise<E2eSubmitResult> => {
        window.__MYRM_E2E_EPH_OPTS__ = {
          hasOpts: Boolean(opts),
          hasEph: Boolean(opts?.ephemeralSubagents),
          keys: opts?.ephemeralSubagents ? Object.keys(opts.ephemeralSubagents) : [],
          at: Date.now(),
        };
        const baselineUsers =
          typeof opts?.baselineUserCount === 'number'
            ? opts.baselineUserCount
            : (window.__MYRM_E2E_CHAT__?.turnSnapshot?.().userCount ?? 0);
        const profile = opts?.profile === 'read' ? 'read' : 'live';
        const result = await submitAndObserveTurn(
          text,
          baselineUsers,
          profile,
          opts?.preserveActionMode === true,
          opts?.ephemeralSubagents,
        );
        window.__MYRM_E2E_CHAT__!.lastSubmitResult = result;
        return result;
      },
      kickoffChatMessage: async (
        text: string,
        opts?: {
          baselineUserCount?: number;
          preserveActionMode?: boolean;
          profile?: SendTurnProfile;
        },
      ): Promise<E2eSubmitResult> => {
        const baselineUsers =
          typeof opts?.baselineUserCount === 'number'
            ? opts.baselineUserCount
            : (window.__MYRM_E2E_CHAT__?.turnSnapshot?.().userCount ?? 0);
        const profile = opts?.profile === 'read' ? 'read' : 'live';
        const result = await submitAndObserveTurn(text, baselineUsers, profile, opts?.preserveActionMode === true);
        window.__MYRM_E2E_CHAT__!.lastSubmitResult = result;
        return result;
      },
      submitAndObserveTurn: async (
        text: string,
        opts?: {
          baselineUserCount?: number;
          preserveActionMode?: boolean;
          profile?: SendTurnProfile;
          ephemeralSubagents?: Record<string, unknown>;
        },
      ): Promise<E2eSubmitResult> => {
        const baselineUsers =
          typeof opts?.baselineUserCount === 'number'
            ? opts.baselineUserCount
            : (window.__MYRM_E2E_CHAT__?.turnSnapshot?.().userCount ?? 0);
        const profile = opts?.profile === 'read' ? 'read' : 'live';
        const result = await submitAndObserveTurn(
          text,
          baselineUsers,
          profile,
          opts?.preserveActionMode === true,
          opts?.ephemeralSubagents,
        );
        window.__MYRM_E2E_CHAT__!.lastSubmitResult = result;
        return result;
      },
      handleSubmit: async () => {
        const resolveMessage = (): string => {
          const fromStore = useChatStore.getState().inputMessage.trim();
          if (fromStore) {
            return fromStore;
          }
          const input = document.querySelector('[data-chat-input]') as HTMLTextAreaElement | null;
          const fromDom = input?.value?.trim() ?? '';
          if (fromDom) {
            flushSync(() => {
              useChatStore.getState().setInputMessage(fromDom);
            });
            return fromDom;
          }
          return '';
        };
        const baselineUsers =
          typeof window.__MYRM_E2E_CHAT__?._submitBaselineUsers === 'number'
            ? window.__MYRM_E2E_CHAT__!._submitBaselineUsers!
            : (window.__MYRM_E2E_CHAT__?.turnSnapshot?.().userCount ?? 0);
        const result = await submitAndObserveTurn(resolveMessage(), baselineUsers, 'live');
        window.__MYRM_E2E_CHAT__!.lastSubmitResult = result;
      },
      getInputMessage: () => useChatStore.getState().inputMessage,
      peekOutboundUserMessage: () => {
        const state = useChatStore.getState();
        const pending = state.pendingExplicitSkillActivation;
        const userText = state.inputMessage;
        if (pending) {
          return buildExplicitSkillWireMessage(pending, userText);
        }
        return userText;
      },
      turnSnapshot: () => {
        const state = useChatStore.getState();
        const users = state.messages.filter((message) => message.role === 'user');
        const assistants = state.messages.filter((message) => message.role === 'assistant');
        const lastAssistant = assistants[assistants.length - 1];
        const assistantText = (() => {
          const content: unknown = lastAssistant?.content;
          if (typeof content === 'string') {
            return content;
          }
          if (Array.isArray(content)) {
            return content
              .map((part) => {
                if (typeof part === 'string') {
                  return part;
                }
                if (part && typeof part === 'object' && 'text' in part) {
                  const text = (part as { text?: unknown }).text;
                  return typeof text === 'string' ? text : '';
                }
                return '';
              })
              .join('');
          }
          return '';
        })();
        const pending = state.pendingExplicitSkillActivation;
        const boundSkillIds = state.agentConfig?.selectedSkillIds ?? [];
        const skillCatalog = useSkillStore.getState();
        const slashBoundSkillResolvedCount = boundSkillIds.length;
        return {
          chatId: state.chatId?.trim() || null,
          userCount: users.length,
          isStreaming: Boolean(state.loading || state.abortController),
          hasOk: /\bOK\b/i.test(assistantText),
          hasDone: /\bDONE\b/i.test(assistantText),
          hasCompletionSignal: /(?:\bOK\b|GOAL_OK|\bDONE\b)/i.test(assistantText),
          lastAssistantSample: assistantText.slice(0, 200),
          lastAssistantHasDoneSkipped: /DONE-SKIPPED/i.test(assistantText),
          clarificationAnswered: lastAssistant?.clarification?.answered === true,
          toolApprovalQueueLen: useToolApprovalStore.getState().queue.length,
          pendingSkillNames: pending?.skillNames ?? [],
          pendingSkillInstruction: pending?.instruction ?? null,
          agentSelectedSkillCount: boundSkillIds.length,
          slashBoundSkillResolvedCount,
          slashSkillCatalogReady: boundSkillIds.length === 0 || slashBoundSkillResolvedCount === boundSkillIds.length,
          marketSkillCount: skillCatalog.marketSkills.length,
        };
      },
      prefetchSlashSkillCatalog: async () => {
        const store = useSkillStore.getState();
        await Promise.all([store.fetchMarketSkills(true), store.fetchLocalSkills()]);
        const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {
          marketSkillCount: 0,
          slashBoundSkillResolvedCount: 0,
          slashSkillCatalogReady: false,
        };
        return {
          marketSkillCount: snap.marketSkillCount ?? 0,
          slashBoundSkillResolvedCount: snap.slashBoundSkillResolvedCount ?? 0,
          slashSkillCatalogReady: snap.slashSkillCatalogReady === true,
          skillStoreError: useSkillStore.getState().error,
        };
      },
      toolApprovalSnapshot: () => ({
        queueLen: useToolApprovalStore.getState().queue.length,
        tools: useToolApprovalStore.getState().queue.map((row) => row.toolName),
      }),
      sseSnapshot: (messageId?: string | null) => {
        const filterId = typeof messageId === 'string' ? messageId.trim() : '';
        if (!filterId) {
          return sseEvents.map((entry) => entry.type);
        }
        return sseEvents.filter((entry) => entry.messageId === filterId).map((entry) => entry.type);
      },
      clearSseSnapshot: () => {
        sseEvents.length = 0;
        sseCaptureMessageId = null;
        sseCaptureLocked = true;
      },
      allocateStreamMessageId: () => useChatStore.getState().allocateNewSessionMessageId(),
      setSseCaptureMessageId: (messageId: string | null | undefined) => {
        sseCaptureMessageId = typeof messageId === 'string' && messageId.trim() ? messageId.trim() : null;
        sseCaptureLocked = false;
      },
      setGoalMode: (enabled: boolean) => {
        flushSync(() => {
          useChatStore.getState().setIsGoalMode(enabled);
        });
      },
      setGoalBudgetTokens: (tokens: number | null) => {
        flushSync(() => {
          useChatStore.getState().setGoalBudgetTokens(tokens);
        });
      },
      setGoalConvergenceWindow: (window: number | null) => {
        flushSync(() => {
          useChatStore.getState().setGoalConvergenceWindow(window);
        });
      },
      getGoalMode: () => useChatStore.getState().isGoalMode,
      getActiveGoalSnapshot: () => {
        const goal = useGoalStore.getState().activeGoal;
        if (!goal) {return null;}
        return {
          status: goal.status,
          reason: goal.reason ?? null,
          objective: goal.objective,
        };
      },
      loadActiveGoalFromApi: async () => {
        const chatId = useChatStore.getState().chatId?.trim();
        if (!chatId) {
          return { ok: false, err: 'no-chat-id' };
        }
        const res = await fetchWithTimeout(`/goals/${chatId}/status`);
        if (!res.ok) {
          return { ok: false, err: `fetch-${res.status}` };
        }
        const data = (await res.json()) as { goal?: Record<string, unknown> };
        if (!data.goal) {
          return { ok: false, err: 'no-goal' };
        }
        const { normalizeGoalState } = await import('@/store/chat/messageStream/streamHelpers');
        useGoalStore.getState().setActiveGoal(normalizeGoalState(data.goal as unknown as GoalStatusPayload));
        return {
          ok: true,
          status: String(data.goal.status ?? ''),
          reason: typeof data.goal.reason === 'string' ? data.goal.reason : null,
        };
      },
      getGoalDraftState: () => {
        const state = useChatStore.getState();
        return {
          composerObjective: state.inputMessage.trim(),
          acceptanceCount: state.goalAcceptanceCriteria?.length ?? 0,
          constraintsCount: state.goalConstraints?.length ?? 0,
          draftButtonDisabled: !state.inputMessage.trim(),
        };
      },
      ephSubagentsStatus: () => {
        const ac = useChatStore.getState().agentConfig;
        return {
          hasConfig: Boolean(ac),
          ephKeys: ac?.ephemeralSubagents ? Object.keys(ac.ephemeralSubagents) : [],
          applied: window.__MYRM_E2E_EPH_APPLIED__ ?? null,
          sendOpts: window.__MYRM_E2E_EPH_OPTS__ ?? null,
        };
      },
      runGoalDraftFromComposer: async () => {
        const objective = useChatStore.getState().inputMessage.trim();
        if (!objective) {
          return { ok: false, err: 'empty-composer' };
        }
        const locale =
          typeof document.documentElement.lang === 'string' && document.documentElement.lang
            ? document.documentElement.lang
            : 'en';
        const res = await fetchWithTimeout(
          '/goals/draft',
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ objective, locale }),
          },
          120_000,
        );
        if (!res.ok) {
          return { ok: false, err: `draft-${res.status}` };
        }
        const data = (await res.json()) as {
          constraints?: string[];
          acceptance_criteria?: Array<Record<string, unknown>>;
        };
        if (data.acceptance_criteria?.length) {
          useChatStore.getState().setGoalAcceptanceCriteria(data.acceptance_criteria);
        }
        if (data.constraints?.length) {
          useChatStore.getState().setGoalConstraints(data.constraints);
        }
        return {
          ok: true,
          acceptanceCount: data.acceptance_criteria?.length ?? 0,
          constraintsCount: data.constraints?.length ?? 0,
        };
      },
      dispatchSystemNotification: (detail: Record<string, unknown>) => {
        window.dispatchEvent(new CustomEvent('system-notification', { detail }));
        const data = detail.data;
        const meta =
          typeof data === 'object' && data !== null && !Array.isArray(data)
            ? (data as Record<string, unknown>).meta_data
            : undefined;
        const kind =
          typeof meta === 'object' && meta !== null && !Array.isArray(meta)
            ? (meta as Record<string, unknown>).kind
            : undefined;
        const chatId =
          typeof meta === 'object' && meta !== null && !Array.isArray(meta)
            ? (meta as Record<string, unknown>).chat_id
            : undefined;
        if (kind === 'background_job_finish' && typeof chatId === 'string' && chatId.trim()) {
          void useGoalStore.getState().refreshActiveGoal(chatId.trim());
          notifyBackgroundTasksChangedForShellJobFinish(meta as Record<string, unknown>);
        }
      },
      dispatchBackgroundJobFinishAndRefresh: async (chatId: string) => {
        const trimmed = chatId.trim();
        if (!trimmed) {
          return { ok: false, err: 'empty-chat-id' };
        }
        const detail = {
          data: {
            meta_data: { kind: 'background_job_finish', chat_id: trimmed },
          },
        };
        window.dispatchEvent(new CustomEvent('system-notification', { detail }));
        await useGoalStore.getState().refreshActiveGoal(trimmed);
        notifyBackgroundTasksChangedForShellJobFinish(detail.data.meta_data as Record<string, unknown>);
        const snap = useGoalStore.getState().activeGoal;
        return {
          ok: true,
          status: snap?.status ?? null,
          reason: snap?.reason ?? null,
        };
      },
      setCurrentBuiltinTools: (tools: string[]) => {
        const nextTools = tools as BuiltinToolId[];
        flushSync(() => {
          useChatStore.getState().setCurrentBuiltinTools([...nextTools]);
        });
      },
      getCurrentBuiltinTools: () => [...useChatStore.getState().currentBuiltinTools],
      setToolsSnapshotForE2e: (tools: ToolSnapshotItem[]) => {
        useToolsSnapshotStore.getState().setTools(tools);
      },
      pinLiteModelForE2e: async (opts?: { preserveActionMode?: boolean }) => {
        const preserveActionMode = shouldPreserveE2eActionMode(
          useChatStore.getState().actionMode,
          Boolean(opts?.preserveActionMode),
        );
        await initProvidersForE2e(preserveActionMode ? { preserveActionMode: true } : undefined);
        if (shouldRunPrepareAutomationSend(preserveActionMode)) {
          prepareAutomationSend();
        }
        // 与 pinBasicModelForE2e 一致：用后端权威配置校验，绕开 store 缓存。
        const authoritative = await fetchE2eProviderConfigBody();
        const serverProviders = authoritative.providers ?? [];
        const serverLitePrimary = authoritative.defaultModelConfig?.liteModel?.primary;
        const storeLitePrimary = useProviderStore.getState().defaultModelConfig?.liteModel?.primary;
        const litePrimary = serverLitePrimary ?? storeLitePrimary;
        if (!litePrimary?.providerId || !litePrimary?.model) {
          throw new Error('e2e-lite-model-unconfigured');
        }
        if (!isModelAvailable(litePrimary, serverProviders)) {
          throw new Error(`e2e-lite-model-unavailable:${litePrimary.providerId}/${litePrimary.model}`);
        }
        const authoritativeConfig = authoritative.defaultModelConfig;
        if (serverProviders.length > 0 || authoritativeConfig) {
          useProviderStore.setState({
            providers: serverProviders.length > 0 ? serverProviders : useProviderStore.getState().providers,
            defaultModelConfig: authoritativeConfig ?? useProviderStore.getState().defaultModelConfig,
          });
        }
        const selection = {
          providerId: litePrimary.providerId,
          model: litePrimary.model,
        };
        flushSync(() => {
          useProviderStore.getState().setFastModeModel(selection);
          const chat = useChatStore.getState();
          if (chat.agentConfig) {
            chat.updateAgentConfig({
              modelSelection: selection,
              enabledBuiltinTools: [...chat.currentBuiltinTools],
            });
            return;
          }
          chat.setAgentConfig({
            modelSelection: selection,
            enabledBuiltinTools: [...chat.currentBuiltinTools],
            selectedSkillIds: [],
            selectedMcpNames: [],
            systemPrompt: '',
            useGlobalInstruction: true,
          });
        });
        return selection;
      },
      pinBasicModelForE2e: async () => {
        // Desktop approval E2E requires tool-capable agent mode; fast/deep can keep send disabled
        // when search configs are intentionally empty under e2e_search_policy("empty").
        prepareAutomationSend();
        await initProvidersForE2e();
        // E2E 权威配置：直接读后端 /api/v1/config/providers，绕开 store 缓存，
        // 保证并行/共享 attach 复用页面时能看到测试 seed 的 corrupt primary。
        const authoritative = await fetchE2eProviderConfigBody();
        const serverProviders = authoritative.providers ?? [];
        const serverBasePrimary = authoritative.defaultModelConfig?.baseModel?.primary;
        const storeBasePrimary = useProviderStore.getState().defaultModelConfig?.baseModel?.primary;
        const primary = serverBasePrimary ?? storeBasePrimary;
        if (!primary?.providerId || !primary?.model) {
          throw new Error('e2e-base-model-unconfigured');
        }
        if (!isModelAvailable(primary, serverProviders)) {
          const base = (resolveE2eApiBase() || getApiBaseUrl()).replace(/\/+$/, '');
          const provider = serverProviders.find((p) => p.id === primary.providerId);
          throw new Error(
            `e2e-base-model-unavailable:${primary.providerId}/${primary.model}` +
              ` base=${base} providerId=${provider?.id ?? '?'} models=${JSON.stringify(provider?.enabledModels ?? [])}`,
          );
        }
        // 用后端权威数据刷新 store（providers + defaultModelConfig），
        // 保证后续发送走测试 seed 的 corrupt primary。
        const authoritativeConfig = authoritative.defaultModelConfig;
        if (serverProviders.length > 0 || authoritativeConfig) {
          useProviderStore.setState({
            providers: serverProviders.length > 0 ? serverProviders : useProviderStore.getState().providers,
            defaultModelConfig: authoritativeConfig ?? useProviderStore.getState().defaultModelConfig,
          });
        }
        const selection = {
          providerId: primary.providerId,
          model: primary.model,
        };
        flushSync(() => {
          useProviderStore.getState().setFastModeModel(selection);
          const chat = useChatStore.getState();
          if (chat.agentConfig) {
            chat.updateAgentConfig({
              modelSelection: selection,
              enabledBuiltinTools: [...chat.currentBuiltinTools],
            });
            return;
          }
          chat.setAgentConfig({
            modelSelection: selection,
            enabledBuiltinTools: [...chat.currentBuiltinTools],
            selectedSkillIds: [],
            selectedMcpNames: [],
            systemPrompt: '',
            useGlobalInstruction: true,
          });
        });
        return selection;
      },
      skipActiveClarificationForE2e: () => {
        const state = useChatStore.getState();
        const pending = [...state.messages]
          .reverse()
          .find((message) => message.role === 'assistant' && message.clarification && !message.clarification.answered);
        if (!pending?.messageId) {
          throw new Error('e2e-no-active-clarification');
        }
        void state.sendMessage('', pending.messageId, undefined, {});
        return { messageId: pending.messageId };
      },
      setBrowserSource: (source: string) => {
        flushSync(() => {
          const chat = useChatStore.getState();
          if (chat.agentConfig) {
            chat.updateAgentConfig({ browserSource: source });
            return;
          }
          chat.setAgentConfig({
            browserSource: source,
            enabledBuiltinTools: [...chat.currentBuiltinTools],
            selectedSkillIds: [],
            selectedMcpNames: [],
            systemPrompt: '',
            useGlobalInstruction: true,
          });
        });
      },
      getBrowserSource: () => useChatStore.getState().agentConfig?.browserSource ?? null,
      ensureComputerUseReady: () => {
        flushSync(() => {
          prepareAutomationSend();
          const chat = useChatStore.getState();
          const tools = chat.currentBuiltinTools.includes('computer_use')
            ? chat.currentBuiltinTools
            : [...chat.currentBuiltinTools, 'computer_use' as BuiltinToolId];
          chat.setCurrentBuiltinTools([...tools]);
        });
        void import('@/store/useDesktopInspectorStore').then(({ default: useDesktopInspectorStore }) => {
          useDesktopInspectorStore.getState().openPanel();
        });
      },
      getActionMode: () => useChatStore.getState().actionMode,
      setActionMode: (mode: ActionMode) => {
        flushSync(() => {
          useChatStore.getState().setActionMode(mode);
        });
      },
      getSearchDepth: () => useChatStore.getState().searchDepth,
      setSearchDepth: (depth: 'normal' | 'deep') => {
        flushSync(() => {
          useChatStore.getState().setSearchDepth(depth);
        });
      },
      getFastSearchProgressSnapshot: () => {
        const chat = useChatStore.getState();
        const assistants = chat.messages.filter((message) => message.role === 'assistant');
        const lastAssistant = assistants[assistants.length - 1];
        const metaSteps = Array.isArray(lastAssistant?.metadata?.progressSteps)
          ? lastAssistant.metadata.progressSteps
          : [];
        const steps = lastAssistant?.progressSteps?.length ? lastAssistant.progressSteps : metaSteps;
        const toolNames = steps.map((step) => String(step.tool_name ?? ''));
        const evictedRefs = steps
          .map((step) => step.evicted_file_ref)
          .filter((ref): ref is string => typeof ref === 'string' && ref.length > 0);
        const content = typeof lastAssistant?.content === 'string' ? lastAssistant.content : '';
        return {
          chatId: chat.chatId?.trim() || null,
          isStreaming: Boolean(chat.loading || chat.abortController),
          toolNames,
          evictedRefs,
          contentSample: content.slice(0, 240),
          mentionsGuido: /Guido van Rossum/i.test(content),
          hasAssistant: Boolean(lastAssistant),
        };
      },
      getDesktopToolProgress: () => {
        const approval = useDesktopControlApprovalStore.getState();
        const chat = useChatStore.getState();
        const messages = chat.messages;
        const assistants = messages.filter((message) => message.role === 'assistant');
        const lastAssistant = assistants[assistants.length - 1];
        const metaSteps = Array.isArray(lastAssistant?.metadata?.progressSteps)
          ? lastAssistant.metadata.progressSteps
          : [];
        const steps = lastAssistant?.progressSteps?.length ? lastAssistant.progressSteps : metaSteps;
        const desktopSteps = steps.filter((step) => String(step.tool_name ?? '').startsWith('desktop_'));
        const completionStatus = String(lastAssistant?.metadata?.completionStatus ?? '');
        const isComplete = completionStatus === 'complete';
        const isStreaming = !isComplete && Boolean(chat.loading || chat.abortController);
        return {
          active: desktopSteps.length > 0,
          isStreaming,
          pending: approval.pending,
          requestId: approval.requestId,
          stepCount: desktopSteps.length,
          lastTool: desktopSteps[desktopSteps.length - 1]?.tool_name ?? '',
        };
      },
      getFirstDesktopDref: () => {
        const pickDref = (refs: Record<string, { role?: string; name?: string }> | undefined): string | null => {
          if (!refs || typeof refs !== 'object') {
            return null;
          }
          const preferredRoles = new Set(['text', 'statictext', 'axtextarea', 'scrollarea']);
          for (const [refId, info] of Object.entries(refs)) {
            const role = String(info?.role ?? '').toLowerCase();
            const normalized = refId.trim().replace(/^@/, '');
            if (preferredRoles.has(role) && normalized.startsWith('d') && normalized.length > 1) {
              return normalized;
            }
          }
          for (const refId of Object.keys(refs).sort()) {
            const normalized = refId.trim().replace(/^@/, '');
            if (normalized.startsWith('d') && normalized.length > 1) {
              return normalized;
            }
          }
          return null;
        };

        const e2eRefs = window.__MYRM_E2E_DESKTOP_REFS__?.refs;
        const fromE2eCache = pickDref(e2eRefs);
        if (fromE2eCache) {
          return fromE2eCache;
        }

        const viewData = useDesktopInspectorStore.getState().viewData;
        return pickDref(viewData?.refs);
      },
      abortActiveStream: () => {
        useChatStore.getState().stopMessage();
      },
      /** Close in-flight SSE only (no cancel API) so a separate agent-stream resume can proceed. */
      releaseActiveStreamForApiResume: () => {
        const chatState = useChatStore.getState();
        const paneId = useWorkspaceStore.getState().panes.find((pane) => pane.chatId === chatState.chatId)?.id;
        const paneAbort = paneId != null ? useWorkspaceStore.getState().getPaneAbortController(paneId) : null;
        const controller = paneAbort ?? chatState.abortController;
        let released = false;
        if (controller && !controller.signal.aborted) {
          controller.abort();
          released = true;
        }
        flushSync(() => {
          useChatStore.setState({
            loading: false,
            abortController: null,
            messageAppeared: true,
          });
        });
        if (paneId) {
          useWorkspaceStore.getState().setPaneAbortController(paneId, null);
        }
        return { ok: true, released };
      },
      retryStreamWithSameMessageId: async (query: string, messageId: string) => {
        await initProvidersForE2e();
        prepareAutomationSend();
        const trimmedId = messageId.trim();
        const trimmedQuery = query.trim();
        if (!trimmedId || !trimmedQuery) {
          return { ok: false, busy: false, err: 'empty-query-or-message-id' };
        }
        const state = useChatStore.getState();
        const modelSelection = getModelSelection(state.actionMode, state.agentConfig);
        if (!modelSelection) {
          return { ok: false, busy: false, err: 'no-model-selection' };
        }
        const abortController = new AbortController();
        const actions = {
          setMessages: useChatStore.getState().setMessages,
          setLoading: (loading: boolean) => useChatStore.setState({ loading }),
          setMessageAppeared: (appeared: boolean) => useChatStore.setState({ messageAppeared: appeared }),
          setHideAttachList: (hide: boolean) => useChatStore.setState({ hideAttachList: hide }),
          setHasUsedImagesInCurrentChat: (hasUsed: boolean) =>
            useChatStore.setState({ hasUsedImagesInCurrentChat: hasUsed }),
          setSelectedModels: (models: typeof state.selectedModels) => useChatStore.setState({ selectedModels: models }),
          setHasUserSelectedModel: (hasSelected: boolean) =>
            useChatStore.setState({ hasUserSelectedModel: hasSelected }),
          clearCurrentSessionMessageId: () => useChatStore.setState({ currentSessionMessageId: null }),
          setIsWorkflowMode: (enabled: boolean) => useChatStore.setState({ isWorkflowMode: enabled }),
          clearPendingWorkflowTemplate: () =>
            useChatStore.setState({
              pendingWorkflowTemplateId: null,
              pendingWorkflowTemplateDisplayName: null,
              pendingWorkflowTemplateArgs: null,
            }),
          _processSuggestions: useChatStore.getState()._processSuggestions,
          scheduleAutoSave: useChatStore.getState().scheduleAutoSave,
          setInputMessage: (message: string) => useChatStore.setState({ inputMessage: message }),
        };
        {
          const win = window as unknown as Record<string, unknown>;
          if (win.__MYRM_E2E_DIRECT_SSE__ !== false) {
            win.__MYRM_E2E_DIRECT_SSE__ = true;
          }
        }
        try {
          await executeStreamWithRetry(
            trimmedQuery,
            trimmedId,
            state,
            actions,
            modelSelection,
            abortController,
            false,
            '',
          );
          return { ok: true, busy: false };
        } catch (error) {
          if (error instanceof AgentBusyError) {
            return { ok: false, busy: true, err: error.message };
          }
          return {
            ok: false,
            busy: false,
            err: error instanceof Error ? error.message : String(error),
          };
        } finally {
          abortController.abort();
        }
      },
      getDesktopApprovalSnapshot: () => {
        const state = useDesktopControlApprovalStore.getState();
        return {
          pending: state.pending,
          requestId: state.requestId,
          reason: state.reason,
          operation: state.operation,
          appName: state.appName,
          requireAppApproval: state.requireAppApproval,
        };
      },
      syncDesktopControlApproval: (payload: {
        request_id: string;
        reason: string;
        operation: string;
        app_name?: string;
        window_title?: string;
        require_app_approval?: boolean;
      }) => {
        useDesktopControlApprovalStore.getState().requestApproval({
          request_id: payload.request_id,
          reason: payload.reason,
          operation: payload.operation,
          app_name: payload.app_name,
          window_title: payload.window_title,
          require_app_approval: payload.require_app_approval,
        });
        void import('@/store/useDesktopInspectorStore').then(({ default: useDesktopInspectorStore }) => {
          useDesktopInspectorStore.getState().openPanel();
        });
      },
      getChatShellState: () => {
        const state = useChatStore.getState();
        let artifactCount = 0;
        let htmlArtifactWithPath = false;
        for (const message of state.messages) {
          const artifacts = message.artifacts ?? [];
          artifactCount += artifacts.length;
          if (
            artifacts.some(
              (artifact) =>
                artifact.type === 'html' && typeof artifact.file_path === 'string' && artifact.file_path.length > 0,
            )
          ) {
            htmlArtifactWithPath = true;
          }
        }
        return {
          chatId: state.chatId?.trim() || null,
          notFound: state.notFound,
          loadError: state.loadError,
          isMessagesLoaded: state.isMessagesLoaded,
          loading: state.loading,
          messageCount: state.messages.length,
          artifactCount,
          htmlArtifactWithPath,
        };
      },
      setLoading: (loading: boolean) => {
        useChatStore.setState({ loading });
      },
      hideApprovalDrawer: () => {
        flushSync(() => {
          useApprovalStore.getState().hideDrawer();
        });
      },
      isApprovalDrawerOpen: () => useApprovalStore.getState().isOpen,
      triggerBrowserTakeover: (payload) => {
        flushSync(() => {
          useBrowserTakeoverStore.getState().requestTakeover({
            reason: payload.reason,
            messageId: payload.messageId ?? 'e2e-takeover-msg',
            ui_mode: payload.ui_mode ?? 'extension',
            auto_detect_completion: payload.auto_detect_completion ?? false,
            url: payload.url,
          });
        });
      },
      getBrowserTakeoverSnapshot: () => {
        const state = useBrowserTakeoverStore.getState();
        return {
          pending: state.pending,
          uiMode: state.uiMode,
          autoDetectCompletion: state.autoDetectCompletion,
          reason: state.reason,
          messageId: state.messageId || null,
        };
      },
      recoverPendingBrowserTakeover: async () => {
        const chatId = useChatStore.getState().chatId;
        const { fetchPendingApprovals } = await import('@/hooks/approval/usePendingApprovalsRecovery');
        const approvals = await fetchPendingApprovals();
        const matching = approvals.filter(
          (approval) =>
            approval.action_type === 'browser_takeover' &&
            approval.status === 'PENDING' &&
            (!chatId || approval.chat_id === chatId),
        );
        for (const approval of matching) {
          useApprovalStore.getState().openApproval(approval);
        }
        const snap = useBrowserTakeoverStore.getState();
        return {
          recovered: matching.length,
          pending: snap.pending,
          uiMode: snap.uiMode,
        };
      },
      getBrowserToolProgress: () => {
        const takeover = useBrowserTakeoverStore.getState();
        const messages = useChatStore.getState().messages;
        const assistants = messages.filter((message) => message.role === 'assistant');
        const lastAssistant = assistants[assistants.length - 1];
        const steps = lastAssistant?.progressSteps ?? [];
        const browserSteps = steps.filter((step) => String(step.tool_name ?? '').startsWith('browser_'));
        return {
          active: browserSteps.length > 0,
          takeoverPending: takeover.pending,
          takeoverUiMode: takeover.pending ? takeover.uiMode : null,
          stepCount: browserSteps.length,
          lastTool: browserSteps[browserSteps.length - 1]?.tool_name ?? '',
        };
      },
      getBrowserInspectorSnapshot: () => {
        const store = useBrowserInspectorStore.getState();
        const activeChatId = useChatStore.getState().chatId?.trim() ?? '';
        const scopedView = selectScopedBrowserViewData(store.viewData, activeChatId);
        const refs = store.viewData?.refs ?? {};
        return {
          isOpen: store.isOpen,
          isBrowserActive: store.isBrowserActive,
          hasScreenshot: Boolean(store.viewData?.screenshotBase64),
          scopedHasScreenshot: Boolean(scopedView?.screenshotBase64),
          sourceChatId: store.viewData?.sourceChatId ?? '',
          activeChatId,
          pageUrl: store.viewData?.pageUrl ?? '',
          pageTitle: store.viewData?.pageTitle ?? '',
          refCount: Object.keys(refs).length,
          updatedAt: store.viewData?.updatedAt ?? null,
        };
      },
      simulateBrowserViewUpdate: async (chatId: string) => {
        const normalizedChatId = chatId.trim();
        if (!normalizedChatId) {
          return { ok: false as const, reason: 'empty-chat-id' };
        }
        const { fileDiffEvents } = await import(
          '@/store/chat/messageStream/handlers/fileDiffEvents'
        );
        const { AgentEventType } = await import('@/store/chat/types');
        const messageId = `e2e-blvc-view-${Date.now()}`;
        await fileDiffEvents({
          data: {
            type: AgentEventType.BROWSER_VIEW_UPDATE,
            messageId,
            data: {
              screenshot_base64: 'e2e-blvc-screenshot',
              mime_type: 'image/jpeg',
              refs: {},
              page_url: 'https://e2e.example/blcv',
              page_title: 'BLCV E2E',
              viewport_width: 1280,
              viewport_height: 720,
            },
          },
          input: '',
          sources: undefined,
          added: false,
          state: {
            messages: [
              {
                messageId,
                chatId: normalizedChatId,
                role: 'assistant',
                content: '',
                createdAt: new Date(),
              },
            ],
            messageAppeared: false,
            loading: false,
            scheduler: {} as import('@/store/chat/messageStream/types').StreamHandlerState['scheduler'],
          },
          actions: {
            setMessages: () => undefined,
            setMessageAppeared: () => undefined,
            setLoading: () => undefined,
            _processSuggestions: async () => undefined,
            scheduleAutoSave: () => undefined,
          },
          recievedMessage: '',
          files: [],
        });
        return { ok: true as const, chatId: normalizedChatId };
      },
      simulateBrowserToolStart: async (chatId: string, toolName = 'browser_navigate_tool') => {
        const normalizedChatId = chatId.trim();
        const normalizedTool = toolName.trim();
        if (!normalizedChatId || !normalizedTool.startsWith('browser_')) {
          return { ok: false as const, reason: 'invalid-args' };
        }
        const { toolLifecycleEvents } = await import(
          '@/store/chat/messageStream/handlers/toolLifecycleEvents'
        );
        const { AgentEventType } = await import('@/store/chat/types');
        const messageId = `e2e-blvc-tool-${Date.now()}`;
        await toolLifecycleEvents({
          data: {
            type: AgentEventType.TOOL_START,
            messageId,
            tool_name: normalizedTool,
          },
          input: '',
          sources: undefined,
          added: false,
          state: {
            messages: [
              {
                messageId,
                chatId: normalizedChatId,
                role: 'assistant',
                content: '',
                createdAt: new Date(),
              },
            ],
            messageAppeared: false,
            loading: false,
            scheduler: {} as import('@/store/chat/messageStream/types').StreamHandlerState['scheduler'],
          },
          actions: {
            setMessages: () => undefined,
            setMessageAppeared: () => undefined,
            setLoading: () => undefined,
            _processSuggestions: async () => undefined,
            scheduleAutoSave: () => undefined,
          },
          recievedMessage: '',
          files: [],
        });
        return { ok: true as const, chatId: normalizedChatId, toolName: normalizedTool };
      },
      getDesktopInspectorSnapshot: () => {
        const store = useDesktopInspectorStore.getState();
        const activeChatId = useChatStore.getState().chatId?.trim() ?? '';
        const scopedView = selectScopedDesktopViewData(store.viewData, activeChatId);
        const refs = store.viewData?.refs ?? {};
        return {
          isOpen: store.isOpen,
          isDesktopActive: store.isDesktopActive,
          hasScreenshot: Boolean(store.viewData?.screenshotBase64),
          scopedHasScreenshot: Boolean(scopedView?.screenshotBase64),
          sourceChatId: store.viewData?.sourceChatId ?? '',
          activeChatId,
          appName: store.viewData?.appName ?? '',
          refCount: Object.keys(refs).length,
          updatedAt: store.viewData?.updatedAt ?? null,
        };
      },
      simulateDesktopViewUpdate: async (chatId: string) => {
        const normalizedChatId = chatId.trim();
        if (!normalizedChatId) {
          return { ok: false as const, reason: 'empty-chat-id' };
        }
        const { fileDiffEvents } = await import(
          '@/store/chat/messageStream/handlers/fileDiffEvents'
        );
        const { AgentEventType } = await import('@/store/chat/types');
        const messageId = `e2e-blvc-desktop-${Date.now()}`;
        await fileDiffEvents({
          data: {
            type: AgentEventType.DESKTOP_VIEW_UPDATE,
            messageId,
            data: {
              screenshot_base64: 'e2e-blvc-desktop-screenshot',
              mime_type: 'image/jpeg',
              refs: {},
              app_name: 'E2E App',
              window_title: 'BLCV Desktop E2E',
              scope: 'screen',
              needs_permission: false,
              viewport_width: 1280,
              viewport_height: 720,
            },
          },
          input: '',
          sources: undefined,
          added: false,
          state: {
            messages: [
              {
                messageId,
                chatId: normalizedChatId,
                role: 'assistant',
                content: '',
                createdAt: new Date(),
              },
            ],
            messageAppeared: false,
            loading: false,
            scheduler: {} as import('@/store/chat/messageStream/types').StreamHandlerState['scheduler'],
          },
          actions: {
            setMessages: () => undefined,
            setMessageAppeared: () => undefined,
            setLoading: () => undefined,
            _processSuggestions: async () => undefined,
            scheduleAutoSave: () => undefined,
          },
          recievedMessage: '',
          files: [],
        });
        return { ok: true as const, chatId: normalizedChatId };
      },
      simulateDesktopControlApprovalRequest: async (chatId: string) => {
        const normalizedChatId = chatId.trim();
        if (!normalizedChatId) {
          return { ok: false as const, reason: 'empty-chat-id' };
        }
        const { fileDiffEvents } = await import(
          '@/store/chat/messageStream/handlers/fileDiffEvents'
        );
        const { AgentEventType } = await import('@/store/chat/types');
        const messageId = `e2e-blvc-desktop-approval-${Date.now()}`;
        await fileDiffEvents({
          data: {
            type: AgentEventType.DESKTOP_CONTROL_APPROVAL_REQUEST,
            messageId,
            data: {
              request_id: `req-${Date.now()}`,
              reason: 'E2E desktop control',
              operation: 'control',
              app_name: 'E2E App',
              window_title: 'BLCV',
              require_app_approval: true,
            },
          },
          input: '',
          sources: undefined,
          added: false,
          state: {
            messages: [
              {
                messageId,
                chatId: normalizedChatId,
                role: 'assistant',
                content: '',
                createdAt: new Date(),
              },
            ],
            messageAppeared: false,
            loading: true,
            scheduler: {} as import('@/store/chat/messageStream/types').StreamHandlerState['scheduler'],
          },
          actions: {
            setMessages: () => undefined,
            setMessageAppeared: () => undefined,
            setLoading: () => undefined,
            _processSuggestions: async () => undefined,
            scheduleAutoSave: () => undefined,
          },
          recievedMessage: '',
          files: [],
        });
        return { ok: true as const, chatId: normalizedChatId };
      },
      dismissBrowserTakeover: () => {
        flushSync(() => {
          useBrowserTakeoverStore.getState().completeTakeover();
        });
      },
      completeBrowserTakeoverWithResume: async () => {
        const snap = useBrowserTakeoverStore.getState();
        if (!snap.pending) {
          return { ok: false, reason: 'not_pending' };
        }
        const storeMessageId = snap.messageId;
        const chatId = useChatStore.getState().chatId;
        flushSync(() => {
          useBrowserTakeoverStore.getState().completeTakeover();
        });
        const { resolveBrowserTakeoverMessageId } = await import('@/store/useApprovalStore');
        const resumeMessageId = resolveBrowserTakeoverMessageId(storeMessageId);
        let resumeStarted = false;
        if (resumeMessageId) {
          void useChatStore
            .getState()
            .sendMessage('', resumeMessageId, undefined, { action: 'completed', message: '' })
            .then(() => {
              console.log('[E2E_TAKEOVER_RESUME] fire-and-forget sendMessage settled');
            })
            .catch((error: unknown) => {
              console.error('[E2E_TAKEOVER_RESUME] fire-and-forget sendMessage failed', error);
            });
          resumeStarted = true;
        }
        return {
          ok: true,
          chatId: chatId ?? null,
          resumeMessageId: resumeMessageId ?? null,
          storeMessageId: storeMessageId ?? null,
          resumeStarted,
        };
      },
      forkFirstContextBranchBookmark: async () => {
        const chatId = useChatStore.getState().chatId;
        if (!chatId) {
          return { ok: false as const, reason: 'no-chat-id' };
        }
        if (useChatStore.getState().loading) {
          return { ok: false as const, reason: 'streaming-blocked' };
        }
        const { forkContextBranch, listContextBranches } = await import('@/services/chat');
        const branches = await listContextBranches(chatId);
        const bookmark = branches[0];
        if (!bookmark?.branch_id) {
          return { ok: false as const, reason: 'no-bookmark', branchCount: branches.length };
        }
        try {
          const label = bookmark.label?.trim() || bookmark.snapshot_path.split(/[/\\]/).pop() || 'Snapshot branch';
          const result = await forkContextBranch(chatId, bookmark.branch_id, label);
          if (!result.new_chat_id) {
            return { ok: false as const, reason: 'missing-new-chat-id' };
          }
          useWorkspaceStore.getState().addPane(result.new_chat_id);
          const target = `/${result.new_chat_id}`;
          window.location.assign(target);
          return { ok: true as const, newChatId: result.new_chat_id, parentChatId: chatId };
        } catch (error) {
          return {
            ok: false as const,
            reason: 'fork-failed',
            error: error instanceof Error ? error.message : String(error),
          };
        }
      },
    } as NonNullable<Window['__MYRM_E2E_CHAT__']>;

    window.__MYRM_E2E_SUBAGENT__ = {
      hydrate: (rows) => {
        flushSync(() => {
          useSubagentStore.getState().setNodes(rows as unknown as SubagentNode[]);
        });
      },
      nodeCount: () => Object.keys(useSubagentStore.getState().nodes).length,
      refresh: () => undefined,
    };

    return () => {
      delete window.__MYRM_E2E_CHAT__;
      delete window.__MYRM_E2E_SUBAGENT__;
      delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
    };
  }, []);

  return null;
}
