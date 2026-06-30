'use client';

/**
 * [INPUT]
 * useChatStore::sendMessage (POS: 发送消息到 Agent);
 * useArtifactPortalStore::dirtyArtifacts (POS: 协同编辑脏状态);
 * useMessageQueue::enqueue (POS: Agent 忙时排队).
 * [OUTPUT] useSelectionAction: 封装「构建上下文 → 注入脏状态 → 发送/排队」的通用 hook。
 * [POS] SelectionToolbar / DocumentSelectionToolbar / ElementPickerToolbar 的公共消息发送逻辑。
 */

import { useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from '@/lib/utils/toast';
import useChatStore from '@/store/useChatStore';
import useArtifactPortalStore from '@/store/useArtifactPortalStore';
import { useMessageQueue } from '@/hooks/useMessageQueue';

interface UseSelectionActionOptions {
  onSent?: () => void;
}

interface SendActionParams {
  message: string;
}

/**
 * 封装 Artifact 内选中交互的通用发送逻辑：
 * 1. 注入所有 dirtyArtifacts 到消息末尾
 * 2. 根据 Agent 是否忙碌决定 sendMessage 或 enqueue
 * 3. 处理 AgentBusyError 降级到排队
 */
export function useSelectionAction({ onSent }: UseSelectionActionOptions = {}) {
  const sendMessage = useChatStore((s) => s.sendMessage);
  const chatId = useChatStore((s) => s.chatId);
  const loading = useChatStore((s) => s.loading);
  const { enqueue } = useMessageQueue(chatId);
  const t = useTranslations('artifacts.selectionToolbar');

  const sendAction = useCallback(
    async ({ message }: SendActionParams) => {
      if (!message) return;

      const dirtyArtifacts = useArtifactPortalStore.getState().getDirtyArtifacts();
      let finalMessage = message;
      for (const [id, content] of Object.entries(dirtyArtifacts)) {
        finalMessage += `\n\n<edited_artifact id="${id}">\n${content}\n</edited_artifact>`;
        useArtifactPortalStore.getState().clearDirtyState(id);
      }

      onSent?.();

      if (loading) {
        enqueue(finalMessage, []);
        toast.info(t('queued'));
      } else {
        try {
          await sendMessage(finalMessage, undefined);
        } catch (err) {
          if (err && typeof err === 'object' && 'name' in err && err.name === 'AgentBusyError') {
            enqueue(finalMessage, []);
            toast.info(t('queued'));
          } else {
            console.error('useSelectionAction: failed to send message', err);
          }
        }
      }
    },
    [sendMessage, loading, enqueue, onSent, t],
  );

  return { sendAction, loading };
}
