/**
 * [INPUT]
 * - @/store/chat/useMessageQueueStore::useMessageQueueStore (POS: 排队消息内存状态源)
 * - @/store/chat/messageQueueStorage::{readStoredQueue, writeStoredQueue} (POS: 排队消息 localStorage 持久化层)
 * - @/store/useChatStore::useChatStore (POS: 聊天状态总线，读取无痕模式)
 * - @/store/chat/types::{ArchiveRestoreAction, File} (POS: Chat domain state and request contracts)
 *
 * [OUTPUT]
 * - useMessageQueue: one chat's queued messages with mutations bound to the chat, persisted unless incognito.
 *
 * [POS]
 * 排队消息的 React 视图层。所有消费者（输入框、工件选区动作）共享同一份队列，因此任何一处入队都对输入框可见；
 * 无痕会话只保留在内存中，不写入 localStorage。
 */

import { useEffect, useMemo } from 'react';
import type { ArchiveRestoreAction, File as ChatFile } from '@/store/chat/types';
import { readStoredQueue, writeStoredQueue } from '@/store/chat/messageQueueStorage';
import { EMPTY_CHAT_QUEUE, useMessageQueueStore } from '@/store/chat/useMessageQueueStore';
import useChatStore from '@/store/useChatStore';
import type { TurnCapabilitySelection } from './turnCapabilityOverrideCore';

export const useMessageQueue = (chatId: string | null | undefined) => {
  const incognito = useChatStore((state) => state.incognitoMode);
  const queue = useMessageQueueStore((state) => (chatId ? state.queues[chatId] : undefined)) ?? EMPTY_CHAT_QUEUE;
  const { items, pausedReason, hydrated } = queue;

  useEffect(() => {
    if (chatId && !incognito) {
      useMessageQueueStore.getState().hydrate(chatId, readStoredQueue(chatId));
    }
  }, [chatId, incognito]);

  useEffect(() => {
    if (chatId && !incognito && hydrated) {
      writeStoredQueue(chatId, { items, pausedReason });
    }
  }, [chatId, incognito, hydrated, items, pausedReason]);

  const actions = useMemo(() => {
    const store = () => useMessageQueueStore.getState();
    return {
      /** Queues a message and returns its 1-based position in the queue (0 when there is no active chat). */
      enqueue: (
        text: string,
        files: ChatFile[],
        archiveRestoreActions?: ArchiveRestoreAction[],
        turnCapabilitySelection?: TurnCapabilitySelection | null,
      ): number => {
        if (!chatId) {
          return 0;
        }
        store().enqueue(chatId, { text, files, archiveRestoreActions, turnCapabilitySelection });
        return store().queues[chatId]?.items.length ?? 0;
      },
      editMessage: (id: string, text: string): void => {
        if (chatId) {
          store().editMessage(chatId, id, text);
        }
      },
      removeMessage: (id: string): void => {
        if (chatId) {
          store().removeMessage(chatId, id);
        }
      },
      clearQueue: (): void => {
        if (chatId) {
          store().clearQueue(chatId);
        }
      },
      reorder: (oldIndex: number, newIndex: number): void => {
        if (chatId) {
          store().reorder(chatId, oldIndex, newIndex);
        }
      },
      setEditingId: (id: string | null): void => {
        if (chatId) {
          store().setEditingId(chatId, id);
        }
      },
      resume: (): void => {
        if (chatId) {
          store().resume(chatId);
        }
      },
    };
  }, [chatId]);

  return { queue: items, pausedReason, editingId: queue.editingId, ...actions };
};
