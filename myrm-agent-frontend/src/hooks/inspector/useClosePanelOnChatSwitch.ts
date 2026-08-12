import { useEffect, useRef } from 'react';

/** Close inspector panel when the user switches chats; avoid closing on TOOL_START with stale sourceChatId. */
export function useClosePanelOnChatSwitch(
  chatId: string,
  isOpen: boolean,
  closePanel: () => void,
): void {
  const prevChatIdRef = useRef(chatId);
  useEffect(() => {
    const prevChatId = prevChatIdRef.current;
    prevChatIdRef.current = chatId;
    if (!chatId || prevChatId === chatId) return;
    if (isOpen) {
      closePanel();
    }
  }, [chatId, isOpen, closePanel]);
}
