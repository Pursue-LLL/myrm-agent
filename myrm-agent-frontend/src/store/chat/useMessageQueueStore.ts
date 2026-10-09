/**
 * [INPUT]
 * - @/store/chat/types::{ArchiveRestoreAction, File} (POS: Chat domain state and request contracts)
 * - @/hooks/message-input/turnCapabilityOverrideCore::TurnCapabilitySelection (POS: 单轮能力覆写核心类型，仅类型引用)
 *
 * [OUTPUT]
 * - useMessageQueueStore: per-chat queue of messages that wait for the agent to become idle.
 * - QueuedMessage / ChatQueue / QueuePauseReason / ClaimOutcome: queue contracts.
 * - selectDrainableHeadId: pure gate deciding whether the head message may be sent now.
 * - QUEUE_DRAIN_DELAYS_MS / resolveDrainDelayMs: delay ladder in front of each (re)send attempt.
 *
 * [POS]
 * Single in-memory source of truth for queued messages, shared by the composer, artifact selection actions
 * and the drain loop (every consumer of one chat sees the same queue). All transitions are pure and synchronous
 * so the drain contract (single flight, edit lock, pause, bounded retries) is testable without React.
 * Persistence is the hook layer's concern (messageQueueStorage.ts), keeping this store free of storage and UI.
 */
import { create } from 'zustand';
import type { ArchiveRestoreAction, File as ChatFile } from '@/store/chat/types';
import type { TurnCapabilitySelection } from '@/hooks/message-input/turnCapabilityOverrideCore';

/**
 * Why a chat's queue stopped sending on its own:
 * - stopped: the user stopped the running reply.
 * - stuck: sending needs the user to act; the busy backoff ran out or the request was refused locally.
 */
export type QueuePauseReason = 'stopped' | 'stuck';

/**
 * How a claimed message left the drain:
 * - consumed: the request was dispatched (or its content handed back to the composer); the message is done.
 * - busy: the server still runs another turn; retry later with backoff.
 * - blocked: the request was refused locally (for example a missing model); retrying is pointless until the user acts.
 */
export type ClaimOutcome = 'consumed' | 'busy' | 'blocked';

export interface QueuedMessage {
  id: string;
  text: string;
  files: ChatFile[];
  archiveRestoreActions?: ArchiveRestoreAction[];
  turnCapabilitySelection?: TurnCapabilitySelection | null;
  timestamp: number;
}

export type NewQueuedMessage = Omit<QueuedMessage, 'id' | 'timestamp'>;

export interface ChatQueue {
  items: QueuedMessage[];
  /** Why automatic sending is suspended; null while the queue drains on its own. */
  pausedReason: QueuePauseReason | null;
  /** Message open in the editor; the drain never takes it, so an edit cannot race a send. */
  editingId: string | null;
  /** Consecutive refused attempts of the head message. */
  failedAttempts: number;
  /** True while a message taken by the drain is still being sent (single flight). */
  claimed: boolean;
  /** Persisted state was merged in; persisting before that would overwrite it. */
  hydrated: boolean;
}

export type StoredQueue = Pick<ChatQueue, 'items' | 'pausedReason'>;

/** Delay before the first attempt, then before each retry of a message the server refused as busy. */
export const QUEUE_DRAIN_DELAYS_MS = [300, 1_000, 3_000, 8_000, 15_000] as const;

export function resolveDrainDelayMs(failedAttempts: number): number {
  const index = Math.min(Math.max(failedAttempts, 0), QUEUE_DRAIN_DELAYS_MS.length - 1);
  return QUEUE_DRAIN_DELAYS_MS[index];
}

export const EMPTY_CHAT_QUEUE: Readonly<ChatQueue> = {
  items: [],
  pausedReason: null,
  editingId: null,
  failedAttempts: 0,
  claimed: false,
  hydrated: false,
};

/** Id of the message the drain may send now, or null while it must wait. A string keeps effect deps primitive. */
export function selectDrainableHeadId(queue: ChatQueue | undefined, agentBusy: boolean): string | null {
  if (!queue || agentBusy || queue.claimed || queue.pausedReason !== null) {
    return null;
  }
  const head = queue.items[0];
  return head && head.id !== queue.editingId ? head.id : null;
}

interface MessageQueueState {
  queues: Record<string, ChatQueue>;
}

interface MessageQueueActions {
  hydrate: (chatId: string, stored: StoredQueue) => void;
  enqueue: (chatId: string, message: NewQueuedMessage) => QueuedMessage;
  editMessage: (chatId: string, id: string, text: string) => void;
  removeMessage: (chatId: string, id: string) => void;
  clearQueue: (chatId: string) => void;
  reorder: (chatId: string, oldIndex: number, newIndex: number) => void;
  setEditingId: (chatId: string, id: string | null) => void;
  /** Stop means stop: queued follow-ups must not start behind the user's back. */
  pauseOnStop: (chatId: string) => void;
  resume: (chatId: string) => void;
  claimHead: (chatId: string) => QueuedMessage | null;
  releaseClaim: (chatId: string, message: QueuedMessage, outcome: ClaimOutcome) => void;
}

type MessageQueueStore = MessageQueueState & MessageQueueActions;

/** An emptied queue has nothing left to pause, edit or retry. */
function settle(queue: ChatQueue): ChatQueue {
  if (queue.items.length > 0 || queue.claimed) {
    return queue;
  }
  return { ...queue, pausedReason: null, editingId: null, failedAttempts: 0 };
}

function patchQueue(
  state: MessageQueueStore,
  chatId: string,
  update: (queue: ChatQueue) => ChatQueue,
): MessageQueueStore {
  const current = state.queues[chatId] ?? EMPTY_CHAT_QUEUE;
  const next = update(current);
  return next === current ? state : { ...state, queues: { ...state.queues, [chatId]: next } };
}

function createQueuedMessage(message: NewQueuedMessage): QueuedMessage {
  return {
    ...message,
    id: `q-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`,
    timestamp: Date.now(),
  };
}

export const useMessageQueueStore = create<MessageQueueStore>()((set, get) => {
  const apply = (chatId: string, update: (queue: ChatQueue) => ChatQueue) =>
    set((state) => patchQueue(state, chatId, update));

  return {
    queues: {},

    hydrate: (chatId, stored) =>
      apply(chatId, (queue) => {
        if (queue.hydrated) {
          return queue;
        }
        const known = new Set(queue.items.map((item) => item.id));
        return {
          ...queue,
          items: [...stored.items.filter((item) => !known.has(item.id)), ...queue.items],
          pausedReason: queue.pausedReason ?? stored.pausedReason,
          hydrated: true,
        };
      }),

    enqueue: (chatId, message) => {
      const queued = createQueuedMessage(message);
      apply(chatId, (queue) => ({ ...queue, items: [...queue.items, queued] }));
      return queued;
    },

    editMessage: (chatId, id, text) =>
      apply(chatId, (queue) =>
        queue.items.some((item) => item.id === id)
          ? { ...queue, items: queue.items.map((item) => (item.id === id ? { ...item, text } : item)) }
          : queue,
      ),

    removeMessage: (chatId, id) =>
      apply(chatId, (queue) =>
        queue.items.some((item) => item.id === id)
          ? settle({
              ...queue,
              items: queue.items.filter((item) => item.id !== id),
              editingId: queue.editingId === id ? null : queue.editingId,
            })
          : queue,
      ),

    clearQueue: (chatId) =>
      apply(chatId, (queue) => (queue.items.length > 0 ? settle({ ...queue, items: [] }) : queue)),

    reorder: (chatId, oldIndex, newIndex) =>
      apply(chatId, (queue) => {
        const { length } = queue.items;
        if (oldIndex === newIndex || oldIndex < 0 || newIndex < 0 || oldIndex >= length || newIndex >= length) {
          return queue;
        }
        const items = [...queue.items];
        const [moved] = items.splice(oldIndex, 1);
        items.splice(newIndex, 0, moved);
        return { ...queue, items };
      }),

    setEditingId: (chatId, id) =>
      apply(chatId, (queue) => {
        if (queue.editingId === id || (id !== null && !queue.items.some((item) => item.id === id))) {
          return queue;
        }
        return { ...queue, editingId: id };
      }),

    pauseOnStop: (chatId) =>
      apply(chatId, (queue) =>
        queue.items.length > 0 && queue.pausedReason === null ? { ...queue, pausedReason: 'stopped' } : queue,
      ),

    resume: (chatId) =>
      apply(chatId, (queue) =>
        queue.pausedReason === null && queue.failedAttempts === 0
          ? queue
          : { ...queue, pausedReason: null, failedAttempts: 0 },
      ),

    claimHead: (chatId) => {
      const queue = get().queues[chatId];
      const head = queue?.items[0];
      if (!queue || !head || queue.claimed || queue.pausedReason !== null || queue.editingId === head.id) {
        return null;
      }
      apply(chatId, (current) => ({ ...current, items: current.items.slice(1), claimed: true }));
      return head;
    },

    releaseClaim: (chatId, message, outcome) =>
      apply(chatId, (queue) => {
        if (outcome === 'consumed') {
          return settle({ ...queue, claimed: false, failedAttempts: 0 });
        }
        const items = queue.items.some((item) => item.id === message.id) ? queue.items : [message, ...queue.items];
        const failedAttempts = outcome === 'busy' ? queue.failedAttempts + 1 : queue.failedAttempts;
        const exhausted = outcome === 'blocked' || failedAttempts >= QUEUE_DRAIN_DELAYS_MS.length;
        return {
          ...queue,
          items,
          claimed: false,
          failedAttempts,
          pausedReason: queue.pausedReason ?? (exhausted ? 'stuck' : null),
        };
      }),
  };
});
