import { beforeEach, describe, expect, it } from 'vitest';

import {
  EMPTY_CHAT_QUEUE,
  QUEUE_DRAIN_DELAYS_MS,
  resolveDrainDelayMs,
  selectDrainableHeadId,
  useMessageQueueStore,
  type ChatQueue,
  type QueuedMessage,
} from '../useMessageQueueStore';

const CHAT = 'chat-1';

const store = () => useMessageQueueStore.getState();
const queueOf = (chatId: string = CHAT): ChatQueue => store().queues[chatId] ?? EMPTY_CHAT_QUEUE;
const texts = (chatId: string = CHAT): string[] => queueOf(chatId).items.map((item) => item.text);

function enqueueAll(...messages: string[]): QueuedMessage[] {
  return messages.map((text) => store().enqueue(CHAT, { text, files: [] }));
}

/** Claims the head and fails it as busy until the queue gives up on it. */
function failHeadAsBusy(times: number): void {
  for (let attempt = 0; attempt < times; attempt += 1) {
    const claimed = store().claimHead(CHAT);
    if (!claimed) {
      throw new Error('expected a claimable head');
    }
    store().releaseClaim(CHAT, claimed, 'busy');
  }
}

describe('useMessageQueueStore', () => {
  beforeEach(() => {
    useMessageQueueStore.setState({ queues: {} });
  });

  describe('enqueue', () => {
    it('appends in FIFO order and stamps unique ids', () => {
      const [first, second] = enqueueAll('first', 'second');

      expect(texts()).toEqual(['first', 'second']);
      expect(first.id).not.toBe(second.id);
      expect(first.timestamp).toBeGreaterThan(0);
    });

    it('keeps the queues of different chats apart', () => {
      store().enqueue('chat-a', { text: 'A', files: [] });
      store().enqueue('chat-b', { text: 'B', files: [] });

      expect(texts('chat-a')).toEqual(['A']);
      expect(texts('chat-b')).toEqual(['B']);
    });
  });

  describe('claimHead / releaseClaim', () => {
    it('hands out the head once and refuses a second claim while it is in flight (single flight)', () => {
      enqueueAll('first', 'second');

      const claimed = store().claimHead(CHAT);

      expect(claimed?.text).toBe('first');
      expect(queueOf().claimed).toBe(true);
      expect(texts()).toEqual(['second']);
      expect(store().claimHead(CHAT)).toBeNull();
    });

    it('lets the next message go once the previous one was consumed', () => {
      enqueueAll('first', 'second');
      const first = store().claimHead(CHAT);
      if (!first) {
        throw new Error('expected a claimed message');
      }

      store().releaseClaim(CHAT, first, 'consumed');

      expect(queueOf().claimed).toBe(false);
      expect(store().claimHead(CHAT)?.text).toBe('second');
    });

    it('returns null for an empty or unknown queue', () => {
      expect(store().claimHead('never-used')).toBeNull();
      store().enqueue(CHAT, { text: 'x', files: [] });
      store().clearQueue(CHAT);
      expect(store().claimHead(CHAT)).toBeNull();
    });

    it('puts a busy-refused message back at the head with its identity intact', () => {
      const [first] = enqueueAll('first', 'second');
      const claimed = store().claimHead(CHAT);
      if (!claimed) {
        throw new Error('expected a claimed message');
      }

      store().releaseClaim(CHAT, claimed, 'busy');

      expect(queueOf().items.map((item) => item.id)[0]).toBe(first.id);
      expect(texts()).toEqual(['first', 'second']);
      expect(queueOf().claimed).toBe(false);
      expect(queueOf().failedAttempts).toBe(1);
      expect(queueOf().pausedReason).toBeNull();
    });

    it('does not duplicate a message that is already back in the queue', () => {
      enqueueAll('only');
      const claimed = store().claimHead(CHAT);
      if (!claimed) {
        throw new Error('expected a claimed message');
      }
      store().releaseClaim(CHAT, claimed, 'busy');
      store().releaseClaim(CHAT, claimed, 'busy');

      expect(texts()).toEqual(['only']);
    });

    it('gives up after the retry ladder is used up and waits for the user (stuck)', () => {
      enqueueAll('stubborn');

      failHeadAsBusy(QUEUE_DRAIN_DELAYS_MS.length - 1);
      expect(queueOf().pausedReason).toBeNull();

      failHeadAsBusy(1);
      expect(queueOf().pausedReason).toBe('stuck');
      expect(queueOf().failedAttempts).toBe(QUEUE_DRAIN_DELAYS_MS.length);
      expect(store().claimHead(CHAT)).toBeNull();
      expect(texts()).toEqual(['stubborn']);
    });

    it('treats a local refusal as stuck immediately instead of retrying', () => {
      enqueueAll('no model configured');
      const claimed = store().claimHead(CHAT);
      if (!claimed) {
        throw new Error('expected a claimed message');
      }

      store().releaseClaim(CHAT, claimed, 'blocked');

      expect(queueOf().pausedReason).toBe('stuck');
      expect(queueOf().failedAttempts).toBe(0);
      expect(texts()).toEqual(['no model configured']);
    });

    it('resets the failure streak after a successful dispatch', () => {
      enqueueAll('a', 'b');
      failHeadAsBusy(2);
      const claimed = store().claimHead(CHAT);
      if (!claimed) {
        throw new Error('expected a claimed message');
      }

      store().releaseClaim(CHAT, claimed, 'consumed');

      expect(queueOf().failedAttempts).toBe(0);
    });

    it('does not let a late failure overwrite the stop pause', () => {
      enqueueAll('a', 'b');
      const claimed = store().claimHead(CHAT);
      if (!claimed) {
        throw new Error('expected a claimed message');
      }
      store().pauseOnStop(CHAT);

      store().releaseClaim(CHAT, claimed, 'blocked');

      expect(queueOf().pausedReason).toBe('stopped');
    });

    it('forgets the pause, the editor and the retry streak once the queue is emptied', () => {
      const [only] = enqueueAll('only');
      failHeadAsBusy(2);
      store().setEditingId(CHAT, only.id);
      store().pauseOnStop(CHAT);
      expect(queueOf()).toMatchObject({ pausedReason: 'stopped', editingId: only.id, failedAttempts: 2 });

      store().removeMessage(CHAT, only.id);

      expect(queueOf()).toMatchObject({ items: [], pausedReason: null, editingId: null, failedAttempts: 0 });
    });
  });

  describe('pause and resume', () => {
    it('pauses a queue with waiting messages when the user stops the turn', () => {
      enqueueAll('follow-up');

      store().pauseOnStop(CHAT);

      expect(queueOf().pausedReason).toBe('stopped');
      expect(store().claimHead(CHAT)).toBeNull();
    });

    it('ignores a stop when nothing is waiting', () => {
      store().pauseOnStop(CHAT);

      expect(store().queues[CHAT]).toBeUndefined();
    });

    it('keeps a stuck queue stuck when the user stops again', () => {
      enqueueAll('stubborn');
      failHeadAsBusy(QUEUE_DRAIN_DELAYS_MS.length);

      store().pauseOnStop(CHAT);

      expect(queueOf().pausedReason).toBe('stuck');
    });

    it('resume clears the pause and the failure streak so sending restarts', () => {
      enqueueAll('stubborn');
      failHeadAsBusy(QUEUE_DRAIN_DELAYS_MS.length);

      store().resume(CHAT);

      expect(queueOf()).toMatchObject({ pausedReason: null, failedAttempts: 0 });
      expect(store().claimHead(CHAT)?.text).toBe('stubborn');
    });

    it('does not notify subscribers when there is nothing to resume', () => {
      enqueueAll('fine');
      const before = store();

      store().resume(CHAT);

      expect(store()).toBe(before);
    });
  });

  describe('editing', () => {
    it('never hands out the message that is open in the editor', () => {
      const [first] = enqueueAll('first', 'second');

      store().setEditingId(CHAT, first.id);

      expect(store().claimHead(CHAT)).toBeNull();

      store().setEditingId(CHAT, null);
      expect(store().claimHead(CHAT)?.text).toBe('first');
    });

    it('ignores ids that are not queued', () => {
      enqueueAll('first');

      store().setEditingId(CHAT, 'ghost');

      expect(queueOf().editingId).toBeNull();
    });

    it('releases the editor when its message is removed', () => {
      const [first, second] = enqueueAll('first', 'second');
      store().setEditingId(CHAT, first.id);

      store().removeMessage(CHAT, first.id);

      expect(queueOf().editingId).toBeNull();
      expect(store().claimHead(CHAT)?.id).toBe(second.id);
    });

    it('keeps the edit when another message is removed', () => {
      const [first, second] = enqueueAll('first', 'second');
      store().setEditingId(CHAT, second.id);

      store().removeMessage(CHAT, first.id);

      expect(queueOf().editingId).toBe(second.id);
    });

    it('edits the text of the addressed message only', () => {
      const [first] = enqueueAll('first', 'second');

      store().editMessage(CHAT, first.id, 'changed');
      store().editMessage(CHAT, 'ghost', 'ignored');

      expect(texts()).toEqual(['changed', 'second']);
    });
  });

  describe('reorder and clear', () => {
    it('moves a message and rejects out-of-range moves', () => {
      enqueueAll('A', 'B', 'C');

      store().reorder(CHAT, 2, 0);
      expect(texts()).toEqual(['C', 'A', 'B']);

      const before = store();
      store().reorder(CHAT, 0, 9);
      store().reorder(CHAT, -1, 1);
      store().reorder(CHAT, 1, 1);
      expect(store()).toBe(before);
    });

    it('clearQueue drops every message and the state that only made sense with them', () => {
      const [first] = enqueueAll('A', 'B');
      store().setEditingId(CHAT, first.id);
      store().pauseOnStop(CHAT);

      store().clearQueue(CHAT);

      expect(queueOf()).toMatchObject({ items: [], pausedReason: null, editingId: null });
    });
  });

  describe('hydrate', () => {
    const stored: QueuedMessage = { id: 'stored-1', text: 'from last session', files: [], timestamp: 1 };

    it('restores the stored queue and marks the chat as hydrated', () => {
      store().hydrate(CHAT, { items: [stored], pausedReason: 'stopped' });

      expect(queueOf()).toMatchObject({ items: [stored], pausedReason: 'stopped', hydrated: true });
    });

    it('keeps messages queued before the restore and puts stored ones first', () => {
      const [live] = enqueueAll('queued early');

      store().hydrate(CHAT, { items: [stored, { ...live }], pausedReason: null });

      expect(queueOf().items.map((item) => item.id)).toEqual(['stored-1', live.id]);
    });

    it('restores only once', () => {
      store().hydrate(CHAT, { items: [stored], pausedReason: null });
      store().removeMessage(CHAT, stored.id);

      store().hydrate(CHAT, { items: [stored], pausedReason: null });

      expect(queueOf().items).toEqual([]);
    });

    it('does not override a pause that already happened in this session', () => {
      enqueueAll('queued early');
      store().pauseOnStop(CHAT);

      store().hydrate(CHAT, { items: [], pausedReason: 'stuck' });

      expect(queueOf().pausedReason).toBe('stopped');
    });
  });

  describe('selectDrainableHeadId', () => {
    const head = { id: 'm1', text: 'x', files: [], timestamp: 1 };
    const ready: ChatQueue = { ...EMPTY_CHAT_QUEUE, items: [head, { ...head, id: 'm2' }] };

    it('returns the head id only when the drain may send now', () => {
      expect(selectDrainableHeadId(ready, false)).toBe('m1');
    });

    it.each([
      ['no queue', undefined, false],
      ['the agent is busy', ready, true],
      ['a message is in flight', { ...ready, claimed: true }, false],
      ['the queue is paused', { ...ready, pausedReason: 'stopped' as const }, false],
      ['the head is being edited', { ...ready, editingId: 'm1' }, false],
      ['the queue is empty', { ...ready, items: [] }, false],
    ])('returns null when %s', (_label, queue, agentBusy) => {
      expect(selectDrainableHeadId(queue, agentBusy)).toBeNull();
    });

    it('still drains when a later message is being edited', () => {
      expect(selectDrainableHeadId({ ...ready, editingId: 'm2' }, false)).toBe('m1');
    });
  });

  describe('resolveDrainDelayMs', () => {
    it('walks the backoff ladder and holds at its last step', () => {
      expect([0, 1, 2, 3, 4, 5, 99].map(resolveDrainDelayMs)).toEqual([300, 1000, 3000, 8000, 15000, 15000, 15000]);
    });

    it('treats a negative streak as the first attempt', () => {
      expect(resolveDrainDelayMs(-3)).toBe(300);
    });
  });
});
