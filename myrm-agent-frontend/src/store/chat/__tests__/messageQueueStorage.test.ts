import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { readStoredQueue, writeStoredQueue } from '../messageQueueStorage';
import type { QueuedMessage } from '../useMessageQueueStore';

const CHAT = 'chat-storage';
const QUEUE_KEY = `myrm_message_queue_${CHAT}`;
const PAUSE_KEY = `myrm_message_queue_paused_${CHAT}`;

const message = (id: string, text: string): QueuedMessage => ({ id, text, files: [], timestamp: 1 });

describe('messageQueueStorage', () => {
  beforeEach(() => {
    sessionStorage.clear();
    localStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('reads an empty queue when nothing was stored', () => {
    expect(readStoredQueue(CHAT)).toEqual({ items: [], pausedReason: null });
  });

  it('round-trips the queue together with its pause marker', () => {
    const items = [message('a', 'first'), message('b', 'second')];

    writeStoredQueue(CHAT, { items, pausedReason: 'stopped' });

    expect(readStoredQueue(CHAT)).toEqual({ items, pausedReason: 'stopped' });
  });

  it('belongs to its own tab: it never reads or writes the storage every tab of the browser shares', () => {
    const otherTab = [message('other-tab', 'queued in another tab')];
    localStorage.setItem(QUEUE_KEY, JSON.stringify(otherTab));
    localStorage.setItem(PAUSE_KEY, 'stopped');

    expect(readStoredQueue(CHAT)).toEqual({ items: [], pausedReason: null });

    writeStoredQueue(CHAT, { items: [message('mine', 'queued here')], pausedReason: null });

    expect(sessionStorage.getItem(QUEUE_KEY)).not.toBeNull();
    expect(JSON.parse(localStorage.getItem(QUEUE_KEY) ?? '[]')).toEqual(otherTab);
    expect(localStorage.getItem(PAUSE_KEY)).toBe('stopped');
  });

  it('drops malformed entries and keeps the valid ones', () => {
    sessionStorage.setItem(
      QUEUE_KEY,
      JSON.stringify([message('ok', 'valid'), null, 'text', { id: 1, text: 'bad id', files: [] }, { id: 'x' }]),
    );

    expect(readStoredQueue(CHAT).items).toEqual([message('ok', 'valid')]);
  });

  it('survives corrupt JSON and non-array payloads', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    sessionStorage.setItem(QUEUE_KEY, '{not json');
    expect(readStoredQueue(CHAT)).toEqual({ items: [], pausedReason: null });

    sessionStorage.setItem(QUEUE_KEY, JSON.stringify({ items: [] }));
    expect(readStoredQueue(CHAT)).toEqual({ items: [], pausedReason: null });
  });

  it('ignores a pause marker that has no messages to hold back or an unknown value', () => {
    sessionStorage.setItem(PAUSE_KEY, 'stopped');
    expect(readStoredQueue(CHAT).pausedReason).toBeNull();

    sessionStorage.setItem(QUEUE_KEY, JSON.stringify([message('a', 'first')]));
    sessionStorage.setItem(PAUSE_KEY, 'something-else');
    expect(readStoredQueue(CHAT).pausedReason).toBeNull();
  });

  it('removes both keys once the queue is empty', () => {
    writeStoredQueue(CHAT, { items: [message('a', 'first')], pausedReason: 'stuck' });

    writeStoredQueue(CHAT, { items: [], pausedReason: null });

    expect(sessionStorage.getItem(QUEUE_KEY)).toBeNull();
    expect(sessionStorage.getItem(PAUSE_KEY)).toBeNull();
  });

  it('clears a stale pause marker when the queue resumes', () => {
    writeStoredQueue(CHAT, { items: [message('a', 'first')], pausedReason: 'stopped' });

    writeStoredQueue(CHAT, { items: [message('a', 'first')], pausedReason: null });

    expect(sessionStorage.getItem(PAUSE_KEY)).toBeNull();
    expect(sessionStorage.getItem(QUEUE_KEY)).not.toBeNull();
  });

  it('keeps chats separate', () => {
    writeStoredQueue('chat-a', { items: [message('a', 'A')], pausedReason: null });
    writeStoredQueue('chat-b', { items: [message('b', 'B')], pausedReason: null });

    expect(readStoredQueue('chat-a').items.map((item) => item.text)).toEqual(['A']);
    expect(readStoredQueue('chat-b').items.map((item) => item.text)).toEqual(['B']);
  });

  it('never throws when the browser refuses the write', () => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    vi.spyOn(sessionStorage, 'setItem').mockImplementation(() => {
      throw new Error('QuotaExceededError');
    });

    expect(() => writeStoredQueue(CHAT, { items: [message('a', 'first')], pausedReason: null })).not.toThrow();
  });
});
