/**
 * [INPUT]
 * - @/services/contextCompaction::compactChat (POS: 上下文压缩的前端服务)
 * - @/lib/utils/toast::toast (POS: 统一 toast)
 *
 * [OUTPUT]
 * - useCompactChat: `/compact` 的确认对话框、「不再提醒」偏好与执行
 *
 * [POS]
 * 聊天输入业务 Hook 的压缩部分：`requestCompact` 按偏好决定直接压缩还是先弹确认，`confirmCompact` 用暂存的聚焦主题压缩；不碰消息提交。
 */

import { useCallback, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { compactChat } from '@/services/contextCompaction';
import { toast } from '@/lib/utils/toast';

const DONT_REMIND_STORAGE_KEY = 'dontRemindCompact';

export function useCompactChat(chatId: string | undefined, loadMessages: (chatId: string) => Promise<void>) {
  const t = useTranslations('chat');
  const [showCompactConfirm, setShowCompactConfirm] = useState(false);
  const [dontRemindCompact, setDontRemindCompact] = useState(false);
  const pendingCompactTopicRef = useRef<string | undefined>(undefined);

  /**
   * 执行压缩操作
   */
  const executeCompact = useCallback(
    async (focusTopic?: string) => {
      if (!chatId) {
        toast.warning(t('compact.noChatId'));
        return;
      }

      if (dontRemindCompact) {
        localStorage.setItem(DONT_REMIND_STORAGE_KEY, 'true');
      }

      const toastId = toast.loading(t('compact.compacting'));
      try {
        const result = await compactChat(chatId, focusTopic);
        if (result.compacted) {
          // The server's echo, not the typed text: a long topic is cut before it is sent, and the toast names what was used.
          const topicHint = result.focus_topic ? ` (${result.focus_topic})` : '';
          toast.success(
            t('compact.success', { count: result.message_count, tokens: result.tokens_saved }) + topicHint,
            {
              id: toastId,
            },
          );
          await loadMessages(chatId);
        } else {
          toast.info(t('compact.skipped', { reason: result.reason ?? '' }), { id: toastId });
        }
      } catch {
        toast.error(t('compact.failed'), { id: toastId });
      }
    },
    [chatId, dontRemindCompact, loadMessages, t],
  );

  const requestCompact = useCallback(
    async (focusTopic?: string) => {
      if (localStorage.getItem(DONT_REMIND_STORAGE_KEY) === 'true') {
        await executeCompact(focusTopic);
      } else {
        pendingCompactTopicRef.current = focusTopic;
        setShowCompactConfirm(true);
      }
    },
    [executeCompact],
  );

  const confirmCompact = useCallback(() => {
    const topic = pendingCompactTopicRef.current;
    pendingCompactTopicRef.current = undefined;
    executeCompact(topic);
  }, [executeCompact]);

  return {
    showCompactConfirm,
    setShowCompactConfirm,
    dontRemindCompact,
    setDontRemindCompact,
    executeCompact,
    requestCompact,
    confirmCompact,
  };
}
