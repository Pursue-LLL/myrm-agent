'use client';

/**
 * [INPUT]
 * - @/store/useChatStore (loading, currentBuiltinTools, stopMessage)
 * - @/store/useDesktopInspectorStore (engagedChatId for active CU turn)
 *
 * [OUTPUT]
 * - useComputerUseEscapeAbort: global Escape aborts an in-flight Computer Use turn (Claude CU parity)
 *
 * [POS]
 * Registered from AppLayout capture phase; only when CU tools are enabled and the agent is running.
 */

import { useEffect } from 'react';
import useChatStore from '@/store/useChatStore';
import useDesktopInspectorStore from '@/store/useDesktopInspectorStore';

function isComputerUseTurnActive(chatId: string | undefined): boolean {
  if (!chatId) {
    return false;
  }
  const { loading, currentBuiltinTools } = useChatStore.getState();
  if (!loading) {
    return false;
  }
  if (currentBuiltinTools.includes('computer_use')) {
    return true;
  }
  const engaged = useDesktopInspectorStore.getState().engagedChatId;
  return engaged === chatId;
}

/**
 * Returns true when the event target is an open modal/dialog layer that should keep Escape local.
 */
function isDialogEscapeTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  return Boolean(target.closest('[role="dialog"], [role="alertdialog"], [data-radix-popper-content-wrapper]'));
}

export function useComputerUseEscapeAbort(): void {
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) {
        return;
      }
      if (event.repeat) {
        return;
      }
      if (isDialogEscapeTarget(event.target)) {
        return;
      }

      const chatId = useChatStore.getState().chatId;
      if (!isComputerUseTurnActive(chatId)) {
        return;
      }

      event.preventDefault();
      event.stopPropagation();
      useChatStore.getState().stopMessage();
    };

    window.addEventListener('keydown', handler, true);
    return () => window.removeEventListener('keydown', handler, true);
  }, []);
}
