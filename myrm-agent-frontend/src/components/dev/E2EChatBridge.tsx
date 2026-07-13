'use client';

import { useLayoutEffect } from 'react';
import { flushSync } from 'react-dom';
import useChatStore from '@/store/useChatStore';

function isLocalDevHost(): boolean {
  if (typeof window === 'undefined') return false;
  const host = window.location.hostname;
  return host === '127.0.0.1' || host === 'localhost';
}

/**
 * CDP Chrome E2E bridge mounted at app shell so it is ready before MessageInput subtree hydrates.
 */
export default function E2EChatBridge() {
  useLayoutEffect(() => {
    if (!isLocalDevHost()) return;

    window.__MYRM_E2E_CHAT__ = {
      __e2eFallback: false,
      setInputMessage: (message: string) => {
        flushSync(() => {
          useChatStore.getState().setInputMessage(message);
        });
      },
      handleSubmit: async () => {
        const state = useChatStore.getState();
        const message = state.inputMessage.trim();
        if (!message) return;
        flushSync(() => {
          state.setInputMessage('');
        });
        await state.sendMessage(message, undefined);
      },
      getInputMessage: () => useChatStore.getState().inputMessage,
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
