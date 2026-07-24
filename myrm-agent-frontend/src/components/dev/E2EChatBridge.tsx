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
 *
 * [POS]
 * App shell dev bridge。在 MessageInput 水合前挂载，供 CDP/MCP E2E 驱动聊天与 Goal 模式（非终端用户功能）。
 */
import { useLayoutEffect } from 'react';
import { flushSync } from 'react-dom';
import { getModelSelection } from '@/store/chat/messageRequest';
import useChatStore from '@/store/useChatStore';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';
import useApprovalStore from '@/store/useApprovalStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useProviderStore from '@/store/useProviderStore';
import useConfigStore from '@/store/useConfigStore';
import type { SearchServiceConfigItem } from '@/store/config/types';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { notifyBackgroundTasksChangedForShellJobFinish } from '@/services/backgroundTasksRefresh';
import type { ActionMode, BuiltinToolId } from '@/store/chat/types';
import { useSubagentStore, type SubagentNode } from '@/store/chat/useSubagentStore';
import { markLocalBackendUnreachable } from '@/lib/backend-health';
import { fetchWithTimeout } from '@/lib/api';
import { getApiBaseUrl, resolveE2eApiBase as resolveInjectedE2eApiBase } from '@/lib/deploy-mode';
import { markPlatformUnreachable } from '@/lib/platform-readiness';
import { isModelAvailable } from '@/lib/model-binding';
import {
  shouldPreserveE2eActionMode,
  shouldRunPrepareAutomationSend,
} from '@/components/dev/e2eChatBridgeSendPolicy';
import { getConfigSyncManager } from '@/services/config/ConfigSyncManager';

function isLocalDevHost(): boolean {
  if (typeof window === 'undefined') return false;
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

async function waitE2eProviderSendReady(deadlineMs: number): Promise<void> {
  while (Date.now() < deadlineMs) {
    prepareAutomationSend();
    const { actionMode, agentConfig } = useChatStore.getState();
    const refreshed = useProviderStore.getState();
    const readyLite = refreshed.defaultModelConfig?.liteModel?.primary;
    if (
      refreshed.isInitialized &&
      getModelSelection(actionMode, agentConfig) !== null &&
      readyLite?.providerId &&
      readyLite?.model
    ) {
      return;
    }
    if (!refreshed.isInitialized) {
      await useProviderStore.getState().initProviders();
    } else if (!readyLite?.providerId || !readyLite?.model) {
      await useProviderStore.getState().retryInit();
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error('e2e-send-not-ready-after-provider-init');
}

type E2eProviderConfigBody = {
  value?: {
    defaultModelConfig?: {
      baseModel?: { primary?: { providerId?: string; model?: string } | null };
      liteModel?: { primary?: { providerId?: string; model?: string } | null };
    };
  };
  defaultModelConfig?: {
    baseModel?: { primary?: { providerId?: string; model?: string } | null };
    liteModel?: { primary?: { providerId?: string; model?: string } | null };
  };
};

function extractSearchServiceConfigs(body: unknown): SearchServiceConfigItem[] {
  if (!body || typeof body !== 'object') {
    return [];
  }
  const record = body as { value?: { searchServiceConfigs?: unknown }; searchServiceConfigs?: unknown };
  const root =
    record.value && typeof record.value === 'object'
      ? record.value
      : (record as { searchServiceConfigs?: unknown });
  const configs = root.searchServiceConfigs;
  return Array.isArray(configs) ? (configs as SearchServiceConfigItem[]) : [];
}

async function fetchSearchServiceConfigsFromApi(apiBase: string): Promise<SearchServiceConfigItem[]> {
  const normalizedApi = apiBase.replace(/\/+$/, '');
  const resp = await fetch(`${normalizedApi}/api/v1/config/searchServices`, { cache: 'no-store' });
  if (!resp.ok) {
    return [];
  }
  const body: unknown = await resp.json();
  return extractSearchServiceConfigs(body);
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
  const e2eApiBase = resolveE2eApiBase();
  if (!e2eApiBase) {
    return { ok: false, err: 'no-e2e-api-base' };
  }
  const blockSearchSync =
    typeof window !== 'undefined' && window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
  const deadline = Date.now() + 15_000;
  let configs: SearchServiceConfigItem[] = [];
  while (Date.now() < deadline) {
    configs = await fetchSearchServiceConfigsFromApi(e2eApiBase);
    if (configs.length > 0 || blockSearchSync) {
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  if (configs.length === 0 && !blockSearchSync) {
    configs = await fetchSearchServiceConfigsFromApi('http://127.0.0.1:8080');
  }
  if (configs.length === 0 && !blockSearchSync) {
    return { ok: false, err: 'empty-search-configs' };
  }
  useConfigStore.setState({ searchServiceConfigs: configs });
  return { ok: true, count: configs.length };
}

async function fetchE2eProviderConfigBody(): Promise<E2eProviderConfigBody> {
  const apiBase = (resolveE2eApiBase() || getApiBaseUrl()).replace(/\/+$/, '');
  const res = await fetch(`${apiBase}/api/v1/config/providers`, { cache: 'no-store' });
  if (!res.ok) {
    throw new Error(`e2e-provider-config-fetch-${res.status}`);
  }
  return (await res.json()) as E2eProviderConfigBody;
}

async function hydrateLiteModelFromConfigApi(): Promise<void> {
  const config = await fetchE2eProviderConfigBody();
  const litePrimary = (config.value ?? config)?.defaultModelConfig?.liteModel?.primary;
  if (!litePrimary?.providerId || !litePrimary?.model) {
    throw new Error('e2e-lite-model-unconfigured');
  }
  flushSync(() => {
    useProviderStore.getState().setLiteModel({
      providerId: litePrimary.providerId,
      model: litePrimary.model,
    });
  });
}

async function hydrateBaseModelFromConfigApi(): Promise<void> {
  const config = await fetchE2eProviderConfigBody();
  const basePrimary = (config.value ?? config)?.defaultModelConfig?.baseModel?.primary;
  if (!basePrimary?.providerId || !basePrimary?.model) {
    throw new Error('e2e-base-model-unconfigured');
  }
  flushSync(() => {
    useProviderStore.getState().setBaseModel({
      providerId: basePrimary.providerId,
      model: basePrimary.model,
    });
  });
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
    const providerState = useProviderStore.getState();
    const litePrimary = providerState.defaultModelConfig?.liteModel?.primary;
    if (
      providerState.isInitialized &&
      getModelSelection(actionMode, agentConfig) !== null &&
      litePrimary?.providerId &&
      litePrimary?.model
    ) {
      return;
    }

    markPlatformUnreachable();
    markLocalBackendUnreachable();
    const normalizedApi = e2eApiBase.replace(/\/+$/, '');
    const workspaceStatus =
      typeof window !== 'undefined' ? window.__MYRM_WORKSPACE_STREAM_STATUS__?.() : undefined;
    const workspaceConnected =
      workspaceStatus?.connected === true &&
      (workspaceStatus.origin ?? '').replace(/\/+$/, '') === normalizedApi;

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
    if (
      typeof window !== 'undefined' &&
      window.__MYRM_E2E_BLOCK_SEARCH_SYNC__
    ) {
      clearSearchServicesForE2e();
    } else {
      await hydrateSearchServicesFromE2eApi();
    }
    await waitE2eProviderSendReady(Date.now() + 120_000);
    return;
  }
  const providerState = useProviderStore.getState();
  if (!providerState.isInitialized) {
    await providerState.initProviders();
  }
  await waitE2eProviderSendReady(Date.now() + 120_000);
}

type E2eSubmitResult = {
  ok: boolean;
  err?: string;
  chatId?: string | null;
  mode?: string;
  debug?: Record<string, unknown>;
};

async function executeE2eChatSend(
  message: string,
  baselineUsers: number,
  waitForStreamCompletion = true,
  preserveActionMode = false,
): Promise<E2eSubmitResult> {
  const trimmed = message.trim();
  if (!trimmed) {
    return { ok: false, err: 'empty-message' };
  }
  try {
    window.__MYRM_E2E_CHAT__?.abortActiveStream?.();
    window.__MYRM_E2E_CHAT__?.releaseActiveStreamForApiResume?.();
    const { actionMode: sendActionMode } = useChatStore.getState();
    const shouldPreserveActionMode = shouldPreserveE2eActionMode(
      sendActionMode,
      preserveActionMode,
    );
    const sessionOpts = shouldPreserveActionMode ? { preserveActionMode: true } : undefined;
    await window.__MYRM_E2E_CHAT__?.ensureChatSession?.(sessionOpts);
    flushSync(() => {
      useChatStore.getState().setInputMessage(trimmed);
    });
    if (!useChatStore.getState().chatId?.trim()) {
      return { ok: false, err: 'no-chat-id' };
    }
    if (!window.__MYRM_E2E_CHAT__?.isSendReady?.()) {
      return {
        ok: false,
        err: 'send-not-ready',
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
        debug: {
          turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.(),
          ...window.__MYRM_E2E_CHAT__?.debugProviderState?.(),
        },
      };
    }
    if (!waitForStreamCompletion) {
      void useChatStore.getState().sendMessage(trimmed, undefined).catch((error) => {
        window.__MYRM_E2E_CHAT__!.lastSubmitResult = {
          ok: false,
          err: error instanceof Error ? error.message : String(error),
          mode: 'kickoffBackgroundError',
        };
      });
      const kickoffDeadline = Date.now() + 45_000;
      while (Date.now() < kickoffDeadline) {
        const chatState = useChatStore.getState();
        const userCount = chatState.messages.filter((msg) => msg.role === 'user').length;
        if (
          chatState.loading
          || chatState.abortController
          || userCount > baselineUsers
        ) {
          const chatId = chatState.chatId?.trim() || '';
          return {
            ok: true,
            chatId,
            mode: 'kickoffStreaming',
            debug: { turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.() },
          };
        }
        await new Promise((resolve) => setTimeout(resolve, 250));
      }
    } else {
      try {
        await useChatStore.getState().sendMessage(trimmed, undefined);
      } catch (error) {
        return {
          ok: false,
          err: error instanceof Error ? error.message : String(error),
          debug: {
            turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.(),
            ...window.__MYRM_E2E_CHAT__?.debugProviderState?.(),
          },
        };
      }
    }
    const chatState = useChatStore.getState();
    const chatId = chatState.chatId?.trim() || '';
    const lastUser = [...chatState.messages].reverse().find((msg) => msg.role === 'user');
    if (lastUser?.sendFailed) {
      return {
        ok: false,
        err: 'send-failed-flag',
        chatId,
        debug: { turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.() },
      };
    }
    if (chatId) {
      const messagesUrl = `${getApiBaseUrl().replace(/\/+$/, '')}/chats/${encodeURIComponent(chatId)}/messages`;
      const apiDeadline = Date.now() + 60_000;
      while (Date.now() < apiDeadline) {
        try {
          const resp = await fetch(messagesUrl, { cache: 'no-store' });
          if (resp.ok) {
            const payload = (await resp.json()) as {
              data?: { messages?: Array<{ role?: string }> };
            };
            const users =
              payload.data?.messages?.filter((entry) => entry.role === 'user').length ?? 0;
            if (users > baselineUsers) {
              return { ok: true, chatId, mode: 'apiConfirmed' };
            }
          }
        } catch {
          // retry until deadline
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      return {
        ok: false,
        err: 'api-user-not-persisted',
        chatId,
        debug: {
          turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.(),
          apiBase: getApiBaseUrl(),
          e2eApiBase: resolveE2eApiBase() || null,
          baselineUsers,
        },
      };
    }
    return {
      ok: false,
      err: 'send-completed-without-progress',
      debug: {
        ...window.__MYRM_E2E_CHAT__?.debugProviderState?.(),
        apiBase: getApiBaseUrl(),
        e2eApiBase: resolveE2eApiBase() || null,
        turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.(),
        baselineUsers,
      },
    };
  } catch (error) {
    return {
      ok: false,
      err: error instanceof Error ? error.message : String(error),
    };
  }
}

export default function E2EChatBridge() {
  useLayoutEffect(() => {
    if (!isLocalDevHost()) return;

    const sseEvents: Array<{ type: string; messageId: string | null }> = [];
    let sseCaptureMessageId: string | null = null;
    let sseCaptureLocked = false;
    (window as Window & { __MYRM_E2E_RECORD_SSE__?: (type: string, messageId?: string | null) => void }).__MYRM_E2E_RECORD_SSE__ = (
      type: string,
      messageId?: string | null,
    ) => {
      if (sseCaptureLocked) {
        const normalizedId =
          typeof messageId === 'string' && messageId.trim() ? messageId.trim() : null;
        if (type !== 'capability_gap' || !normalizedId) {
          return;
        }
        sseCaptureMessageId = normalizedId;
        sseCaptureLocked = false;
      }
      const normalizedId =
        typeof messageId === 'string' && messageId.trim() ? messageId.trim() : null;
      if (sseCaptureMessageId && normalizedId !== sseCaptureMessageId) {
        return;
      }
      sseEvents.push({
        type,
        messageId: normalizedId,
      });
      if (sseEvents.length > 64) {
        sseEvents.splice(0, sseEvents.length - 64);
      }
    };

    window.__MYRM_E2E_CHAT__ = {
      __e2eFallback: false,
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
      syncSearchServicesFromE2eApi: hydrateSearchServicesFromE2eApi,
      clearSearchServicesForE2e,
      debugProviderState: () => {
        const { isInitialized, providers, defaultModelConfig } = useProviderStore.getState();
        const { actionMode, agentConfig, chatId, currentSessionMessageId } = useChatStore.getState();
        const selection = getModelSelection(actionMode, agentConfig);
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
            state.chatId === id &&
            (state.notFound || state.loadError || !state.isMessagesLoaded || state.loading);
          if (needsForcedReload) {
            useChatStore.setState({
              chatId: '',
              notFound: false,
              loadError: false,
              isMessagesLoaded: false,
              loading: false,
            });
          }
          useChatStore.getState().initializeChat(id);
        });
        const deadline = Date.now() + 60_000;
        while (Date.now() < deadline) {
          const state = useChatStore.getState();
          if (
            state.chatId === id &&
            state.isMessagesLoaded &&
            !state.notFound &&
            !state.loadError &&
            !state.loading
          ) {
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, 200));
        }
        const finalState = useChatStore.getState();
        throw new Error(
          `attach-timeout chatId=${finalState.chatId} notFound=${finalState.notFound} loadError=${finalState.loadError} loaded=${finalState.isMessagesLoaded}`,
        );
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
        flushSync(() => {
          prepareAutomationSend();
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
            label.includes('steer')
            || label.includes('guidance')
            || label.includes('转向')
            || label.includes('指导')
          );
        }) as HTMLButtonElement | undefined;
        if (steerBtn && !steerBtn.disabled) {
          steerBtn.click();
          return { ok: true, mode: 'steerClick' };
        }
        const baselineUsers = window.__MYRM_E2E_CHAT__?.turnSnapshot?.().userCount ?? 0;
        const sendResult = await executeE2eChatSend(trimmed, baselineUsers);
        return sendResult.ok
          ? { ok: true, mode: 'steerSendFallback', detail: sendResult }
          : { ok: false, err: 'steer-fallback-send-failed', detail: sendResult };
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
        },
      ): Promise<E2eSubmitResult> => {
        const baselineUsers =
          typeof opts?.baselineUserCount === 'number'
            ? opts.baselineUserCount
            : (window.__MYRM_E2E_CHAT__?.turnSnapshot?.().userCount ?? 0);
        const waitForStreamCompletion = opts?.waitForStreamCompletion !== false;
        const result = await executeE2eChatSend(
          text,
          baselineUsers,
          waitForStreamCompletion,
          opts?.preserveActionMode === true,
        );
        window.__MYRM_E2E_CHAT__!.lastSubmitResult = result;
        return result;
      },
      kickoffChatMessage: async (
        text: string,
        opts?: { baselineUserCount?: number; preserveActionMode?: boolean },
      ): Promise<E2eSubmitResult> => {
        const baselineUsers =
          typeof opts?.baselineUserCount === 'number'
            ? opts.baselineUserCount
            : (window.__MYRM_E2E_CHAT__?.turnSnapshot?.().userCount ?? 0);
        const result = await executeE2eChatSend(
          text,
          baselineUsers,
          false,
          opts?.preserveActionMode === true,
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
        const result = await executeE2eChatSend(resolveMessage(), baselineUsers);
        window.__MYRM_E2E_CHAT__!.lastSubmitResult = result;
      },
      getInputMessage: () => useChatStore.getState().inputMessage,
      turnSnapshot: () => {
        const state = useChatStore.getState();
        const users = state.messages.filter((message) => message.role === 'user');
        const assistants = state.messages.filter((message) => message.role === 'assistant');
        const lastAssistant = assistants[assistants.length - 1];
        const assistantText = typeof lastAssistant?.content === 'string' ? lastAssistant.content : '';
        return {
          chatId: state.chatId?.trim() || null,
          userCount: users.length,
          isStreaming: Boolean(state.loading || state.abortController),
          hasOk: /\bOK\b/i.test(assistantText),
          hasDone: /\bDONE\b/i.test(assistantText),
          lastAssistantSample: assistantText.slice(0, 200),
          lastAssistantHasDoneSkipped: /DONE-SKIPPED/i.test(assistantText),
          clarificationAnswered: lastAssistant?.clarification?.answered === true,
          toolApprovalQueueLen: useToolApprovalStore.getState().queue.length,
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
        return sseEvents
          .filter((entry) => entry.messageId === filterId)
          .map((entry) => entry.type);
      },
      clearSseSnapshot: () => {
        sseEvents.length = 0;
        sseCaptureMessageId = null;
        sseCaptureLocked = true;
      },
      allocateStreamMessageId: () => useChatStore.getState().allocateNewSessionMessageId(),
      setSseCaptureMessageId: (messageId: string | null | undefined) => {
        sseCaptureMessageId =
          typeof messageId === 'string' && messageId.trim() ? messageId.trim() : null;
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
        if (!goal) return null;
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
        useGoalStore.getState().setActiveGoal(normalizeGoalState(data.goal));
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
        const kind = typeof meta === 'object' && meta !== null && !Array.isArray(meta)
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
      setCurrentBuiltinTools: (tools: BuiltinToolId[]) => {
        flushSync(() => {
          useChatStore.getState().setCurrentBuiltinTools([...tools]);
        });
      },
      getCurrentBuiltinTools: () => [...useChatStore.getState().currentBuiltinTools],
      pinLiteModelForE2e: async () => {
        await initProvidersForE2e();
        prepareAutomationSend();
        let { defaultModelConfig, providers } = useProviderStore.getState();
        let litePrimary = defaultModelConfig?.liteModel?.primary;
        if (!litePrimary?.providerId || !litePrimary?.model) {
          await hydrateLiteModelFromConfigApi();
          ({ defaultModelConfig, providers } = useProviderStore.getState());
          litePrimary = defaultModelConfig?.liteModel?.primary;
        }
        if (!litePrimary?.providerId || !litePrimary?.model) {
          throw new Error('e2e-lite-model-unconfigured');
        }
        if (!isModelAvailable(litePrimary, providers)) {
          throw new Error(
            `e2e-lite-model-unavailable:${litePrimary.providerId}/${litePrimary.model}`,
          );
        }
        const selection = {
          providerId: litePrimary.providerId,
          model: litePrimary.model,
        };
        flushSync(() => {
          useProviderStore.getState().setFastModeModel(selection);
          const chat = useChatStore.getState();
          if (chat.agentConfig) {
            chat.updateAgentConfig({ modelSelection: selection });
            return;
          }
          chat.setAgentConfig({
            modelSelection: selection,
            enabledBuiltinTools: [...chat.currentBuiltinTools],
            selectedSkillIds: [],
            selectedMcpNames: [],
            systemPrompt: '',
          });
        });
        return selection;
      },
      pinBasicModelForE2e: async () => {
        await initProvidersForE2e();
        let { defaultModelConfig, providers } = useProviderStore.getState();
        let basePrimary = defaultModelConfig?.baseModel?.primary;
        if (!basePrimary?.providerId || !basePrimary?.model) {
          await hydrateBaseModelFromConfigApi();
          ({ defaultModelConfig, providers } = useProviderStore.getState());
          basePrimary = defaultModelConfig?.baseModel?.primary;
        }
        if (!basePrimary?.providerId || !basePrimary?.model) {
          throw new Error('e2e-base-model-unconfigured');
        }
        if (!isModelAvailable(basePrimary, providers)) {
          throw new Error(
            `e2e-base-model-unavailable:${basePrimary.providerId}/${basePrimary.model}`,
          );
        }
        const selection = {
          providerId: basePrimary.providerId,
          model: basePrimary.model,
        };
        flushSync(() => {
          useProviderStore.getState().setFastModeModel(selection);
          const chat = useChatStore.getState();
          if (chat.agentConfig) {
            chat.updateAgentConfig({ modelSelection: selection });
            return;
          }
          chat.setAgentConfig({
            modelSelection: selection,
            enabledBuiltinTools: [...chat.currentBuiltinTools],
            selectedSkillIds: [],
            selectedMcpNames: [],
            systemPrompt: '',
          });
        });
        return selection;
      },
      skipActiveClarificationForE2e: () => {
        const state = useChatStore.getState();
        const pending = [...state.messages]
          .reverse()
          .find(
            (message) =>
              message.role === 'assistant' &&
              message.clarification &&
              !message.clarification.answered,
          );
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
        const steps = lastAssistant?.progressSteps?.length
          ? lastAssistant.progressSteps
          : metaSteps;
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
        const steps = lastAssistant?.progressSteps?.length
          ? lastAssistant.progressSteps
          : metaSteps;
        const desktopSteps = steps.filter((step) =>
          String(step.tool_name ?? '').startsWith('desktop_'),
        );
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
        const messages = useChatStore.getState().messages;
        for (let index = messages.length - 1; index >= 0; index -= 1) {
          const message = messages[index];
          if (message.role !== 'assistant') {
            continue;
          }
          const chunks: string[] = [];
          if (typeof message.content === 'string') {
            chunks.push(message.content);
          }
          const metaSteps = Array.isArray(message.metadata?.progressSteps)
            ? message.metadata.progressSteps
            : [];
          const steps = message.progressSteps?.length ? message.progressSteps : metaSteps;
          for (const step of steps) {
            if (typeof step.stdout === 'string') {
              chunks.push(step.stdout);
            }
            if (typeof step.items === 'string') {
              chunks.push(step.items);
            }
          }
          const match = chunks.join('\n').match(/@(d\d+)\b/);
          if (match) {
            return match[1];
          }
        }
        return null;
      },
      abortActiveStream: () => {
        useChatStore.getState().stopMessage();
      },
      /** Close in-flight SSE only (no cancel API) so a separate agent-stream resume can proceed. */
      releaseActiveStreamForApiResume: () => {
        const chatState = useChatStore.getState();
        const paneId = useWorkspaceStore.getState().panes.find((pane) => pane.chatId === chatState.chatId)?.id;
        const paneAbort =
          paneId != null ? useWorkspaceStore.getState().getPaneAbortController(paneId) : null;
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
        return {
          chatId: state.chatId?.trim() || null,
          notFound: state.notFound,
          loadError: state.loadError,
          isMessagesLoaded: state.isMessagesLoaded,
          loading: state.loading,
          messageCount: state.messages.length,
        };
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
        };
      },
      recoverPendingBrowserTakeover: async () => {
        const chatId = useChatStore.getState().chatId;
        const { fetchPendingApprovals } = await import('@/hooks/usePendingApprovalsRecovery');
        const approvals = await fetchPendingApprovals();
        const matching = approvals.filter(
          (approval) =>
            approval.action_type === 'browser_takeover'
            && approval.status === 'PENDING'
            && (!chatId || approval.chat_id === chatId),
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
        const browserSteps = steps.filter((step) =>
          String(step.tool_name ?? '').startsWith('browser_'),
        );
        return {
          active: browserSteps.length > 0,
          takeoverPending: takeover.pending,
          takeoverUiMode: takeover.pending ? takeover.uiMode : null,
          stepCount: browserSteps.length,
          lastTool: browserSteps[browserSteps.length - 1]?.tool_name ?? '',
        };
      },
      dismissBrowserTakeover: () => {
        flushSync(() => {
          useBrowserTakeoverStore.getState().completeTakeover();
        });
      },
    };

    window.__MYRM_E2E_SUBAGENT__ = {
      hydrate: (rows) => {
        flushSync(() => {
          useSubagentStore.getState().setNodes(rows as SubagentNode[]);
        });
      },
      nodeCount: () => Object.keys(useSubagentStore.getState().nodes).length,
      refresh: () => undefined,
    };

    return () => {
      delete window.__MYRM_E2E_CHAT__;
      delete window.__MYRM_E2E_SUBAGENT__;
    };
  }, []);

  return null;
}
