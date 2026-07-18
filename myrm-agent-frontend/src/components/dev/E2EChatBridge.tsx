'use client';

/**
 * [INPUT]
 * - @/store/useChatStore::useChatStore (POS: 聊天 Zustand store 的业务分层)
 * - @/store/useProviderStore::useProviderStore (POS: Provider 配置 store)
 * - @/store/chat/messageRequest::getModelSelection (POS: 发送前模型选择解析)
 *
 * [OUTPUT]
 * - E2EChatBridge: localhost dev-only `window.__MYRM_E2E_CHAT__` for CDP Chrome E2E
 *
 * [POS]
 * App shell dev bridge。在 MessageInput 水合前挂载，供 CDP/MCP E2E 驱动聊天与 Goal 模式（非终端用户功能）。
 */
import { useLayoutEffect } from 'react';
import { flushSync } from 'react-dom';
import { getModelSelection } from '@/store/chat/messageRequest';
import useChatStore from '@/store/useChatStore';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';
import useProviderStore from '@/store/useProviderStore';
import type { BuiltinToolId } from '@/store/chat/types';
import { useSubagentStore, type SubagentNode } from '@/store/chat/useSubagentStore';
import { markLocalBackendUnreachable } from '@/lib/backend-health';
import { markPlatformUnreachable } from '@/lib/platform-readiness';

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

async function initProvidersForE2e(): Promise<void> {
  const e2eApiBase = typeof window.__MYRM_E2E_API_BASE__ === 'string' ? window.__MYRM_E2E_API_BASE__.trim() : '';
  if (e2eApiBase) {
    markPlatformUnreachable();
    markLocalBackendUnreachable();
    const deadline = Date.now() + 60_000;
    let ready = false;
    while (Date.now() < deadline) {
      if (await probePrivateBackendReady(e2eApiBase)) {
        ready = true;
        break;
      }
      await new Promise((resolve) => setTimeout(resolve, 500));
    }
    if (!ready) {
      throw new Error('e2e-private-backend-not-ready');
    }
    await useProviderStore.getState().retryInit();
    const sendReadyDeadline = Date.now() + 60_000;
    while (Date.now() < sendReadyDeadline) {
      prepareAutomationSend();
      const { actionMode, agentConfig } = useChatStore.getState();
      if (
        useProviderStore.getState().isInitialized &&
        getModelSelection(actionMode, agentConfig) !== null
      ) {
        return;
      }
      await new Promise((resolve) => setTimeout(resolve, 200));
    }
    throw new Error('e2e-send-not-ready-after-provider-init');
  }
  const providerState = useProviderStore.getState();
  if (!providerState.isInitialized) {
    await providerState.initProviders();
  }
}

export default function E2EChatBridge() {
  useLayoutEffect(() => {
    if (!isLocalDevHost()) return;

    window.__MYRM_E2E_CHAT__ = {
      __e2eFallback: false,
      ensureProviders: initProvidersForE2e,
      prepareAutomationSend,
      isProvidersInitialized: () => useProviderStore.getState().isInitialized,
      isSendReady: () => {
        if (!useProviderStore.getState().isInitialized) {
          return false;
        }
        prepareAutomationSend();
        const { actionMode, agentConfig } = useChatStore.getState();
        return getModelSelection(actionMode, agentConfig) !== null;
      },
      debugProviderState: () => {
        const { isInitialized, providers, defaultModelConfig } = useProviderStore.getState();
        const { actionMode, agentConfig, chatId } = useChatStore.getState();
        const selection = getModelSelection(actionMode, agentConfig);
        return {
          isInitialized,
          actionMode,
          chatId,
          providerIds: providers.map((p) => p.id),
          enabledProviderIds: providers.filter((p) => p.isEnabled).map((p) => p.id),
          primary: defaultModelConfig?.baseModel?.primary ?? null,
          agentModelSelection: agentConfig?.modelSelection ?? null,
          selection: selection ? { providerId: selection.providerId, model: selection.model } : null,
        };
      },
      ensureChatSession: async () => {
        await initProvidersForE2e();
        prepareAutomationSend();
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
      handleSubmit: async () => {
        const message = useChatStore.getState().inputMessage.trim();
        if (!message) {
          window.__MYRM_E2E_CHAT__!.lastSubmitResult = { ok: false, err: 'empty-message' };
          return;
        }
        try {
          await window.__MYRM_E2E_CHAT__?.ensureChatSession?.();
          prepareAutomationSend();
          if (!useChatStore.getState().chatId?.trim()) {
            window.__MYRM_E2E_CHAT__!.lastSubmitResult = { ok: false, err: 'no-chat-id' };
            return;
          }
          if (!window.__MYRM_E2E_CHAT__?.isSendReady?.()) {
            window.__MYRM_E2E_CHAT__!.lastSubmitResult = {
              ok: false,
              err: 'send-not-ready',
              debug: window.__MYRM_E2E_CHAT__?.debugProviderState?.(),
            };
            return;
          }
          const baselineUsers = window.__MYRM_E2E_CHAT__?.turnSnapshot?.().userCount ?? 0;
          void useChatStore.getState().sendMessage(message, undefined);
          const deadline = Date.now() + 20_000;
          while (Date.now() < deadline) {
            const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.();
            const chatState = useChatStore.getState();
            const userCount = snap?.userCount ?? 0;
            if (userCount > baselineUsers && (chatState.loading || Boolean(chatState.abortController))) {
              window.__MYRM_E2E_CHAT__!.lastSubmitResult = {
                ok: true,
                chatId: chatState.chatId,
              };
              return;
            }
            await new Promise((resolve) => setTimeout(resolve, 200));
          }
          window.__MYRM_E2E_CHAT__!.lastSubmitResult = {
            ok: false,
            err: 'send-no-stream',
            debug: {
              ...window.__MYRM_E2E_CHAT__?.debugProviderState?.(),
              e2eApiBase: typeof window.__MYRM_E2E_API_BASE__ === 'string' ? window.__MYRM_E2E_API_BASE__ : null,
              turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.(),
            },
          };
        } catch (error) {
          window.__MYRM_E2E_CHAT__!.lastSubmitResult = {
            ok: false,
            err: error instanceof Error ? error.message : String(error),
          };
        }
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
          lastAssistantSample: assistantText.slice(0, 200),
        };
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
      getGoalMode: () => useChatStore.getState().isGoalMode,
      setCurrentBuiltinTools: (tools: BuiltinToolId[]) => {
        flushSync(() => {
          useChatStore.getState().setCurrentBuiltinTools([...tools]);
        });
      },
      getCurrentBuiltinTools: () => [...useChatStore.getState().currentBuiltinTools],
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
      getDesktopToolProgress: () => {
        const approval = useDesktopControlApprovalStore.getState();
        const messages = useChatStore.getState().messages;
        const assistants = messages.filter((message) => message.role === 'assistant');
        const lastAssistant = assistants[assistants.length - 1];
        const steps = lastAssistant?.progressSteps ?? [];
        const desktopSteps = steps.filter((step) =>
          String(step.tool_name ?? '').startsWith('desktop_'),
        );
        return {
          active: desktopSteps.length > 0,
          pending: approval.pending,
          requestId: approval.requestId,
          stepCount: desktopSteps.length,
          lastTool: desktopSteps[desktopSteps.length - 1]?.tool_name ?? '',
        };
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
