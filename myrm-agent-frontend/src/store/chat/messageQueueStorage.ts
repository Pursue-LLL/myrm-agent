/**
 * [INPUT]
 * - @/store/chat/useMessageQueueStore::{QueuedMessage, QueuePauseReason, StoredQueue} (POS: 排队消息内存状态源)
 *
 * [OUTPUT]
 * - readStoredQueue: restore one chat's queued messages and pause marker from localStorage.
 * - writeStoredQueue: persist (or clear) them.
 *
 * [POS]
 * localStorage 持久化层。队列内容与暂停标记分键存储，条目逐个校验，损坏数据只丢弃坏项而不拖垮整个队列。
 * 附件以元数据形式存储（id/fileUrl/localPath），发送只依赖这些稳定引用；乐观预览 URL 刷新后失效，不参与发送。
 */
import type { QueuedMessage, QueuePauseReason, StoredQueue } from '@/store/chat/useMessageQueueStore';

const QUEUE_KEY_PREFIX = 'myrm_message_queue_';
const PAUSE_KEY_PREFIX = 'myrm_message_queue_paused_';

const EMPTY_STORED_QUEUE: StoredQueue = { items: [], pausedReason: null };

function isQueuedMessage(value: unknown): value is QueuedMessage {
  if (typeof value !== 'object' || value === null) {
    return false;
  }
  const candidate = value as Partial<QueuedMessage>;
  return typeof candidate.id === 'string' && typeof candidate.text === 'string' && Array.isArray(candidate.files);
}

function isPauseReason(value: string | null): value is QueuePauseReason {
  return value === 'stopped' || value === 'stuck';
}

export function readStoredQueue(chatId: string): StoredQueue {
  if (typeof window === 'undefined') {
    return EMPTY_STORED_QUEUE;
  }
  try {
    const rawItems = localStorage.getItem(`${QUEUE_KEY_PREFIX}${chatId}`);
    const parsed: unknown = rawItems ? JSON.parse(rawItems) : [];
    const items = Array.isArray(parsed) ? parsed.filter(isQueuedMessage) : [];
    const rawPause = localStorage.getItem(`${PAUSE_KEY_PREFIX}${chatId}`);
    return { items, pausedReason: items.length > 0 && isPauseReason(rawPause) ? rawPause : null };
  } catch (error) {
    console.warn('Failed to restore the message queue from localStorage', error);
    return EMPTY_STORED_QUEUE;
  }
}

export function writeStoredQueue(chatId: string, queue: StoredQueue): void {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    const queueKey = `${QUEUE_KEY_PREFIX}${chatId}`;
    const pauseKey = `${PAUSE_KEY_PREFIX}${chatId}`;
    if (queue.items.length === 0) {
      localStorage.removeItem(queueKey);
      localStorage.removeItem(pauseKey);
      return;
    }
    localStorage.setItem(queueKey, JSON.stringify(queue.items));
    if (queue.pausedReason) {
      localStorage.setItem(pauseKey, queue.pausedReason);
    } else {
      localStorage.removeItem(pauseKey);
    }
  } catch (error) {
    console.warn('Failed to persist the message queue to localStorage', error);
  }
}
