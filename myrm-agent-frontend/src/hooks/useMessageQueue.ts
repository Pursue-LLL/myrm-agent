/**
 * [INPUT]
 * - @/store/chat/types::ArchiveRestoreAction (POS: Chat domain state and request contracts)
 *
 * [OUTPUT]
 * - useMessageQueue: persistent per-chat queued message state with optional typed restore actions.
 *
 * [POS]
 * 消息排队状态机。保存等待发送的文本、附件和结构化恢复动作，确保忙碌重试不丢控制协议。
 */

import { useState, useEffect, useCallback } from 'react';
import type { ArchiveRestoreAction, File as ChatFile } from '@/store/chat/types';

const QUEUE_STORAGE_KEY_PREFIX = 'myrm_message_queue_';

export interface QueuedMessage {
  id: string;
  text: string;
  files: ChatFile[];
  archiveRestoreActions?: ArchiveRestoreAction[];
  timestamp: number;
}

export const useMessageQueue = (chatId: string | null | undefined) => {
  const [queue, setQueue] = useState<QueuedMessage[]>([]);

  // Load queue from localStorage on mount or chatId change
  useEffect(() => {
    if (!chatId || typeof window === 'undefined') {
      setQueue([]);
      return;
    }

    const storageKey = `${QUEUE_STORAGE_KEY_PREFIX}${chatId}`;
    try {
      const storedQueue = localStorage.getItem(storageKey);
      if (storedQueue) {
        // Note: File objects cannot be fully serialized to localStorage.
        // For a robust implementation, we'd need IndexedDB or to only store text/metadata.
        // For now, we restore the text and timestamp, but files will be lost across reloads.
        const parsed = JSON.parse(storedQueue);
        if (Array.isArray(parsed)) {
          setQueue(parsed);
        }
      } else {
        setQueue([]);
      }
    } catch (e) {
      console.error('Failed to load message queue from localStorage', e);
      setQueue([]);
    }
  }, [chatId]);

  // Save queue to localStorage whenever it changes
  useEffect(() => {
    if (!chatId || typeof window === 'undefined') return;

    const storageKey = `${QUEUE_STORAGE_KEY_PREFIX}${chatId}`;
    try {
      if (queue.length > 0) {
        const serializableQueue = queue.map((msg) => ({
          ...msg,
          files: msg.files,
        }));
        localStorage.setItem(storageKey, JSON.stringify(serializableQueue));
      } else {
        localStorage.removeItem(storageKey);
      }
    } catch (e) {
      console.error('Failed to save message queue to localStorage', e);
    }
  }, [queue, chatId]);

  const enqueue = useCallback((text: string, files: ChatFile[], archiveRestoreActions?: ArchiveRestoreAction[]) => {
    const newMessage: QueuedMessage = {
      id: Math.random().toString(36).substring(2, 9),
      text,
      files,
      archiveRestoreActions,
      timestamp: Date.now(),
    };
    setQueue((prev) => [...prev, newMessage]);
    return newMessage;
  }, []);

  const dequeue = useCallback(() => {
    if (queue.length === 0) return null;
    const message = queue[0];
    setQueue((prev) => prev.slice(1));
    return message;
  }, [queue]);

  const removeMessage = useCallback((id: string) => {
    setQueue((prev) => prev.filter((msg) => msg.id !== id));
  }, []);

  const clearQueue = useCallback(() => {
    setQueue([]);
  }, []);

  // For 409 Conflict: put the message back at the front of the queue
  const requeue = useCallback((message: QueuedMessage) => {
    setQueue((prev) => {
      // Avoid duplicates if it's already there
      if (prev.some((m) => m.id === message.id)) return prev;
      return [message, ...prev];
    });
  }, []);

  return {
    queue,
    enqueue,
    dequeue,
    removeMessage,
    clearQueue,
    requeue,
    hasQueuedMessages: queue.length > 0,
  };
};
