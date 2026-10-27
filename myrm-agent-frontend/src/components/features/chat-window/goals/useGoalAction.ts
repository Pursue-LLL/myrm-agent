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
 * Sends the goal controls, one at a time per chat: a press that arrives while another control of that chat is still
 * out is ignored, so a double click neither repeats the request nor shows its toast twice. A control that is out for
 * one chat does not hold the controls of another.
 *
 * `run` resolves whether the server took the action; a held note, a refusal or a failure leaves the goal as it was.
 * `pendingAction` is the control of the current chat that is out, for the buttons to wait on.
 */
export function useGoalAction(chatId: string | null | undefined) {
  const t = useTranslations('Goal');
  const [pendingByChat, setPendingByChat] = useState<Readonly<Record<string, GoalAction>>>({});
  const outChatIds = useRef(new Set<string>());

  const run = useCallback(
    async (action: GoalAction, note?: string): Promise<boolean> => {
      if (!chatId || outChatIds.current.has(chatId)) {
        return false;
      }
      outChatIds.current.add(chatId);
      setPendingByChat((current) => ({ ...current, [chatId]: action }));
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
        outChatIds.current.delete(chatId);
        setPendingByChat((current) => Object.fromEntries(Object.entries(current).filter(([id]) => id !== chatId)));
      }
    },
    [chatId, t],
  );

  return { run, pendingAction: (chatId ? pendingByChat[chatId] : undefined) ?? null };
}
