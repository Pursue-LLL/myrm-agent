/**
 * [INPUT]
 * @/services/chat::getMessages (POS: Chat API client)
 * ./messageHydration::parseMessages (POS: persisted message normalization)
 * @/store/useChatStore (POS: open-chat state)
 *
 * [OUTPUT]
 * refreshOpenChatTranscript: Pull the newest persisted page into the open chat without touching composer state.
 *
 * [POS]
 * In-place transcript sync for changes that land on an open chat outside any stream: an SSE reconnect, finished
 * background work, an approval the timeout already resolved. Unlike initializeChat / loadMessages it never toggles
 * loading flags, resets session config, attaches to a turn or clears attachments, and a failed fetch leaves the
 * visible transcript untouched.
 */

import { getMessages } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { parseMessages } from './messageHydration';

const TAIL_PAGE_SIZE = 10;

const refreshesInFlight = new Set<string>();

/** A turn that owns the store streams state the DB has not persisted yet, so it must not be overwritten. */
function isRefreshable(chatId: string): boolean {
  const state = useChatStore.getState();
  return state.chatId === chatId && !state.loading && !state.abortController;
}

export async function refreshOpenChatTranscript(chatId: string | undefined): Promise<void> {
  if (!chatId || refreshesInFlight.has(chatId) || !isRefreshable(chatId)) {
    return;
  }
  refreshesInFlight.add(chatId);
  try {
    const page = await getMessages(chatId, { limit: TAIL_PAGE_SIZE, silent: true });
    // A turn may have started while the request was in flight.
    if (!isRefreshable(chatId)) {
      return;
    }
    const tail = parseMessages(page.messages);
    if (tail.length === 0) {
      return;
    }
    useChatStore.getState().updateMessages((draft) => {
      const tailById = new Map(tail.map((message) => [message.messageId, message]));
      const localIds = new Set(draft.messages.map((message) => message.messageId));
      const overlapsLocal = draft.messages.some((message) => tailById.has(message.messageId));
      if (!overlapsLocal) {
        // The chat moved past everything held locally: restart from the fresh tail so no gap hides mid-transcript.
        draft.messages = tail;
        draft.hasMoreMessages = page.has_more;
        draft.nextCursor = page.next_cursor;
        return;
      }
      // The DB row wins where both sides hold a message; local-only rows (older pages, a row not yet persisted) stay.
      draft.messages = [
        ...draft.messages.map((message) => tailById.get(message.messageId) ?? message),
        ...tail.filter((message) => !localIds.has(message.messageId)),
      ];
    });
  } catch (error) {
    console.error('Failed to refresh chat transcript:', error, chatId);
  } finally {
    refreshesInFlight.delete(chatId);
  }
}
