/**
 * [INPUT]
 * @/services/chat::getMessages (POS: Chat API client)
 * ./messageHydration::parseMessages (POS: persisted message normalization)
 * @/store/useChatStore (POS: open-chat state)
 *
 * [OUTPUT]
 * refreshOpenChatTranscript: Append the persisted turns an open chat does not show yet, without touching composer state.
 * mergeStoredTail: Pure merge of a persisted tail page into the rows already on screen.
 *
 * [POS]
 * In-place transcript sync for rows that land on an open chat outside any stream: an SSE reconnect, finished
 * background work. Rows already on screen are never rewritten, so store-injected fields and card state survive; only
 * turns the screen has never seen are appended. Unlike initializeChat / loadMessages it never toggles loading flags,
 * resets session config, attaches to a turn or clears attachments, and a failed fetch leaves the visible transcript
 * untouched.
 */

import { getMessages } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { parseMessages } from './messageHydration';
import type { Message } from './types';

const TAIL_PAGE_SIZE = 10;

const refreshesInFlight = new Set<string>();

/**
 * Rows of one turn share this key: a streamed assistant row is keyed by its request id, while its stored rows carry
 * UUID ids and name that request in `requestMessageId`. The role is part of the key because the user row of a turn is
 * stored under the very request id its assistant row streams under.
 */
function turnKey(message: Message): string {
  const turnId =
    message.role === 'assistant' && message.requestMessageId ? message.requestMessageId : message.messageId;
  return `${message.role}:${turnId}`;
}

/**
 * Merge a persisted tail page into the rows on screen by identity, never by counting rows: a turn that paused and
 * resumed is one row on screen (the resume streams into the paused row) yet one stored row per stream. A stored row is
 * already shown when its turn is on screen, or when it names an on-screen assistant row as its request (a resume sent
 * from a row hydrated from the DB). The rest belong to turns the screen has never seen and are appended in stored
 * order.
 * Returns `local` itself when nothing is missing, and null when the tail shares nothing with `local`.
 */
export function mergeStoredTail(local: Message[], tail: Message[]): Message[] | null {
  const shownTurns = new Set(local.map(turnKey));
  const shownAssistantIds = new Set(local.filter((m) => m.role === 'assistant').map((m) => m.messageId));
  const isShown = (row: Message): boolean =>
    shownTurns.has(turnKey(row)) ||
    (row.role === 'assistant' && !!row.requestMessageId && shownAssistantIds.has(row.requestMessageId));

  const missing = tail.filter((row) => !isShown(row));
  if (missing.length === tail.length) {
    return null;
  }
  return missing.length === 0 ? local : [...local, ...missing];
}

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
    const store = useChatStore.getState();
    const merged = mergeStoredTail(store.messages, tail);
    if (merged === store.messages) {
      return;
    }
    store.updateMessages((draft) => {
      draft.messages = merged ?? tail;
      if (merged === null) {
        // The chat moved past everything held locally: restart from the fresh tail so no gap hides mid-transcript.
        draft.hasMoreMessages = page.has_more;
        draft.nextCursor = page.next_cursor;
      }
    });
  } catch (error) {
    console.error('Failed to refresh chat transcript:', error, chatId);
  } finally {
    refreshesInFlight.delete(chatId);
  }
}
