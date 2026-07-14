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
import useProviderStore from '@/store/useProviderStore';

function isLocalDevHost(): boolean {
  if (typeof window === 'undefined') return false;
  const host = window.location.hostname;
  return host === '127.0.0.1' || host === 'localhost';
}

export default function E2EChatBridge() {
  useLayoutEffect(() => {
    if (!isLocalDevHost()) return;

    window.__MYRM_E2E_CHAT__ = {
      __e2eFallback: false,
      ensureProviders: async () => {
        const providerState = useProviderStore.getState();
        if (!providerState.isInitialized) {
          await providerState.initProviders();
        }
      },
      isProvidersInitialized: () => useProviderStore.getState().isInitialized,
      isSendReady: () => {
        if (!useProviderStore.getState().isInitialized) {
          return false;
        }
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
          selection: selection
            ? { providerId: selection.providerId, model: selection.model }
            : null,
        };
      },
      ensureChatSession: async () => {
        const providerState = useProviderStore.getState();
        if (!providerState.isInitialized) {
          await providerState.initProviders();
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
        const providerState = useProviderStore.getState();
        if (!providerState.isInitialized) {
          await providerState.initProviders();
        }
        flushSync(() => {
          useChatStore.getState().initializeChat(id);
        });
        const deadline = Date.now() + 60_000;
        while (Date.now() < deadline) {
          const state = useChatStore.getState();
          if (state.chatId === id && !state.loading) {
            return;
          }
          await new Promise((resolve) => setTimeout(resolve, 200));
        }
        throw new Error('attach-timeout');
      },
      resetChat: () => {
        flushSync(() => {
          useChatStore.getState().initializeChat(undefined);
        });
      },
      setInputMessage: (message: string) => {
        flushSync(() => {
          useChatStore.getState().setInputMessage(message);
        });
      },
      handleSubmit: () => {
        const message = useChatStore.getState().inputMessage.trim();
        if (!message) {
          window.__MYRM_E2E_CHAT__!.lastSubmitResult = { ok: false, err: 'empty-message' };
          return;
        }
        void (async () => {
          try {
            await window.__MYRM_E2E_CHAT__?.ensureChatSession?.();
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
            void useChatStore.getState().sendMessage(message, undefined);
            window.__MYRM_E2E_CHAT__!.lastSubmitResult = {
              ok: true,
              chatId: useChatStore.getState().chatId,
            };
          } catch (error) {
            window.__MYRM_E2E_CHAT__!.lastSubmitResult = {
              ok: false,
              err: error instanceof Error ? error.message : String(error),
            };
          }
        })();
      },
      getInputMessage: () => useChatStore.getState().inputMessage,
      turnSnapshot: () => {
        const state = useChatStore.getState();
        const users = state.messages.filter((message) => message.role === 'user');
        const assistants = state.messages.filter((message) => message.role === 'assistant');
        const lastAssistant = assistants[assistants.length - 1];
        const assistantText =
          typeof lastAssistant?.content === 'string' ? lastAssistant.content : '';
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
    };

    return () => {
      delete window.__MYRM_E2E_CHAT__;
    };
  }, []);

  return null;
}
