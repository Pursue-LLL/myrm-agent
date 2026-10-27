'use client';

import { useCallback, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { postGoalAction } from '@/store/chat/goals/goalActionClient';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import type { GoalAction, GoalStatus } from './goalStatusTypes';

const STATUS_AFTER_ACTION: Record<GoalAction, GoalStatus> = {
  pause: 'paused',
  resume: 'active',
  reject: 'active',
  unwait: 'active',
  cancel: 'cancelled',
  approve: 'complete',
};

/**
 * Sends the goal controls of one chat, one at a time: a press that arrives while another control is still out is
 * ignored, so a double click neither repeats the request nor shows its toast twice.
 *
 * `run` resolves whether the server took the action; a held note, a refusal or a failure leaves the goal as it was.
 * `pendingAction` is the control that is out, for the buttons to wait on.
 */
export function useGoalAction(chatId: string | null | undefined) {
  const t = useTranslations('Goal');
  const [pendingAction, setPendingAction] = useState<GoalAction | null>(null);
  const isOut = useRef(false);

  const run = useCallback(
    async (action: GoalAction, note?: string): Promise<boolean> => {
      if (!chatId || isOut.current) {
        return false;
      }
      isOut.current = true;
      setPendingAction(action);
      try {
        const outcome = await postGoalAction(chatId, action, note);
        if (outcome === 'busy') {
          toast.error(t('goalActionBusy'));
        } else if (outcome === 'failed') {
          toast.error(t(`goalActionFailed_${action}` as 'goalActionFailed_pause'));
        } else if (outcome === 'done') {
          toast.success(t(`goalActionSuccess_${action}` as 'goalActionSuccess_pause'));
          // Only a pause note is a status reason; the note of a rejected review is the agent's next message.
          const reason = action === 'pause' ? note?.trim() || undefined : undefined;
          // A chat opened while the request was out is not this chat: the store drops a status that is no longer its own.
          useGoalStore.getState().updateGoalStatus(chatId, STATUS_AFTER_ACTION[action], reason);
        }
        return outcome === 'done';
      } finally {
        isOut.current = false;
        setPendingAction(null);
      }
    },
    [chatId, t],
  );

  return { run, pendingAction };
}
