/**
 * [INPUT]
 * - window event `system-notification` (POS: 服务端系统通知，meta_data 带会话 id 与种类)
 * - @/store/chat/chatTranscriptRefresh::refreshOpenChatTranscript (POS: 无损刷新已打开的转录)
 * - @/store/chat/goals/useGoalStore (POS: 当前会话的目标状态)
 *
 * [OUTPUT]
 * - useChatSystemNotifications: 只对当前会话响应系统通知
 *   - snapshot_created：弹出快照已创建的提示
 *   - background_job_finish / voice_background_task_done：重新读取转录
 *   - goal_needs_review / goal_usage_limit：刷新当前目标
 *
 * [POS]
 * ChatWindow 的系统通知层。其他会话的通知一律忽略。
 */

import { useEffect } from 'react';
import { ShieldCheck } from 'lucide-react';
import { useTranslations } from 'next-intl';
import { toast } from '@/hooks/shared/useToast';
import { refreshOpenChatTranscript } from '@/store/chat/chatTranscriptRefresh';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';

export function useChatSystemNotifications(id: string | undefined): void {
  const snapshotT = useTranslations('chat.snapshot');

  useEffect(() => {
    const handleSystemNotification = (e: Event) => {
      const customEvent = e as CustomEvent<{ data: unknown }>;
      const meta = (customEvent.detail.data as { meta_data?: Record<string, unknown> } | undefined)?.meta_data || {};

      if (meta?.type === 'snapshot_created' && meta?.chat_id === id) {
        toast({
          title: snapshotT('createdTitle'),
          description: (
            <div className="flex items-center gap-2">
              <ShieldCheck className="w-4 h-4 text-green-500" />
              <span>{snapshotT(`createdMessage.${meta.action ?? 'unknown'}`)}</span>
            </div>
          ),
          variant: 'default',
        });
      }

      if (
        meta?.chat_id === id &&
        (meta?.kind === 'background_job_finish' || meta?.kind === 'voice_background_task_done')
      ) {
        void refreshOpenChatTranscript(id);
      }

      if ((meta?.kind === 'goal_needs_review' || meta?.kind === 'goal_usage_limit') && id && meta?.chat_id === id) {
        void useGoalStore.getState().refreshActiveGoal(id);
      }
    };

    window.addEventListener('system-notification', handleSystemNotification);
    return () => window.removeEventListener('system-notification', handleSystemNotification);
  }, [id, snapshotT]);
}
