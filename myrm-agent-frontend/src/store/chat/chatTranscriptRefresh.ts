/**
 * [INPUT]
 * @/services/chat::getMessages (POS: Chat API client)
 * ./messageHydration::parseMessages (POS: persisted message normalization)
 * @/store/useChatStore (POS: open-chat state)
 *
 * [OUTPUT]
 * refreshOpenChatTranscript: Add the persisted rows an open chat does not show yet, without touching composer state.
 * mergeStoredTail: Pure merge of a persisted tail page into the rows already on screen.
 *
 * [POS]
 * In-place transcript sync for changes that land on an open chat outside any stream: an SSE reconnect, finished
 * background work, an approval the timeout already resolved. Rows already on screen are never rewritten, so
 * store-injected fields and card state survive; only missing rows are added. Unlike initializeChat / loadMessages it
 * never toggles loading flags, resets session config, attaches to a turn or clears attachments, and a failed fetch
 * leaves the visible transcript untouched.
 */

import { getMessages } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { parseMessages } from './messageHydration';
import type { Message } from './types';

const TAIL_PAGE_SIZE = 10;

const refreshesInFlight = new Set<string>();

/**
 * Rows of one turn share a key. A streamed assistant row is keyed by its request id while its stored twin has a
 * UUID id and carries that request id, so matching on `messageId` alone would show every finished turn twice.
 */
function turnKey(message: Message): string {
  const turnId =
    message.role === 'assistant' && message.requestMessageId ? message.requestMessageId : message.messageId;
  return `${message.role}:${turnId}`;
}

function countByKey(messages: Message[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const message of messages) {
    const key = turnKey(message);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

/**
 * Merge a persisted tail page into the rows on screen. A stored row counts as shown when its id is on screen, or
 * when its turn already has that many rows on screen; the rest are inserted behind their turn, else appended.
 * Returns `local` itself when nothing is missing, and null when the tail shares nothing with `local`.
 */
export function mergeStoredTail(local: Message[], tail: Message[]): Message[] | null {
  const localIds = new Set(local.map((message) => message.messageId));
  const shownPerTurn = countByKey(local);
  const seenPerTurn = new Map<string, number>();
  const missing: Message[] = [];
  let sharesRows = false;
  for (const row of tail) {
    const key = turnKey(row);
    const seen = (seenPerTurn.get(key) ?? 0) + 1;
    seenPerTurn.set(key, seen);
    if (localIds.has(row.messageId) || seen <= (shownPerTurn.get(key) ?? 0)) {
      sharesRows = true;
    } else {
      missing.push(row);
    }
  }
  if (!sharesRows) {
    return null;
  }
  if (missing.length === 0) {
    return local;
  }
  const merged = [...local];
  for (const row of missing) {
    const key = turnKey(row);
    const lastOfTurn = merged.findLastIndex((message) => turnKey(message) === key);
    merged.splice(lastOfTurn === -1 ? merged.length : lastOfTurn + 1, 0, row);
  }
  return merged;
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
