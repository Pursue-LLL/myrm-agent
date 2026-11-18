/**
 * [INPUT]
 * - @/services/contextCompaction::runManualCompaction, describeCompactSkip, COMPACT_FAILED_NOTICE, DONT_REMIND_COMPACT_STORAGE_KEY (POS: 手动压缩、没压缩时的提示、「不再提醒」偏好键)
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
import {
  COMPACT_FAILED_NOTICE,
  DONT_REMIND_COMPACT_STORAGE_KEY,
  describeCompactSkip,
  runManualCompaction,
} from '@/services/contextCompaction';
import { toast } from '@/lib/utils/toast';

export function useCompactChat(chatId: string | undefined) {
  const t = useTranslations('chat');
  // The notices carry absolute locale keys, shared with the `/compact` command and the strategy panel.
  const tNotice = useTranslations();
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
        localStorage.setItem(DONT_REMIND_COMPACT_STORAGE_KEY, 'true');
      }

      const toastId = toast.loading(t('compact.compacting'));
      try {
        const result = await runManualCompaction(chatId, focusTopic);
        if (result.compacted) {
          // The server's echo, not the typed text: a long topic is cut before it is sent, and the toast names what was used.
          const topicHint = result.focus_topic ? ` (${result.focus_topic})` : '';
          toast.success(
            t('compact.success', { count: result.message_count, tokens: result.tokens_saved }) + topicHint,
            {
              id: toastId,
            },
          );
        } else {
          const { messageKey, severity } = describeCompactSkip(result.reason);
          toast[severity](tNotice(messageKey), { id: toastId });
        }
      } catch {
        toast.error(tNotice(COMPACT_FAILED_NOTICE.messageKey), { id: toastId });
      }
    },
    [chatId, dontRemindCompact, t, tNotice],
  );

  const requestCompact = useCallback(
    async (focusTopic?: string) => {
      if (localStorage.getItem(DONT_REMIND_COMPACT_STORAGE_KEY) === 'true') {
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
