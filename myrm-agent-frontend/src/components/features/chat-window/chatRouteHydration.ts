/**
 * [INPUT]
 * - useChatStore from '@/store/useChatStore'
 * - ChatState from '@/store/chat/types'
 *
 * [OUTPUT]
 * - isChatRouteHydratedForId: whether the chat store already holds the conversation a route opens
 * - subscribeChatRouteHydrated: calls back each time that answer flips, never for other store writes
 *
 * [POS]
 * Hydration predicate of ChatWindow. The window re-creates its whole chat view (message list, composer and every
 * fetch that runs when they mount) when hydration flips, so a store write that leaves the answer unchanged, such
 * as a typed key or a knowledge-base selection sync, must not reach the callback.
 */

import type { ChatState } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';

type HydrationFields = Pick<ChatState, 'chatId' | 'isMessagesLoaded' | 'messages' | 'compactedSummary'>;

function isHydrated(state: HydrationFields, chatId: string): boolean {
  return (
    state.chatId === chatId &&
    state.isMessagesLoaded &&
    (state.messages.length > 0 || Boolean(state.compactedSummary?.trim()))
  );
}

export function isChatRouteHydratedForId(chatId: string | undefined): boolean {
  return chatId ? isHydrated(useChatStore.getState(), chatId) : false;
}

export function subscribeChatRouteHydrated(chatId: string | undefined, onChange: () => void): () => void {
  if (!chatId) {
    return () => {};
  }
  return useChatStore.subscribe((state, previous) => {
    if (isHydrated(state, chatId) !== isHydrated(previous, chatId)) {
      onChange();
    }
  });
}
