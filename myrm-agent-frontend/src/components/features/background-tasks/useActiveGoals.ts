'use client';

import { useCallback, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { fetchWithTimeout } from '@/lib/api';
import { postGoalAction } from '@/store/chat/goals/goalActionClient';
import { toast } from '@/lib/utils/toast';
import type { ActiveGoal, GoalPanelAction } from './backgroundTasksPanel.constants';

/**
 * The goals running in every chat, and the controls the panel offers on them.
 *
 * A goal takes one control at a time: a press on a goal whose previous control is still out is ignored, and
 * `pendingSessionIds` names those goals for their buttons to wait on. The goal list is refreshed before the buttons
 * are released, so a control is never offered for the state the goal just left.
 */
export function useActiveGoals() {
  const t = useTranslations('backgroundTasks');
  const tGoal = useTranslations('Goal');
  const [activeGoals, setActiveGoals] = useState<ActiveGoal[]>([]);
  const [pendingSessionIds, setPendingSessionIds] = useState<ReadonlySet<string>>(() => new Set());
  const outSessionIds = useRef(new Set<string>());

  const fetchActiveGoals = useCallback(async () => {
    try {
      const res = await fetchWithTimeout('/goals/active');
      if (!res.ok) {
        return;
      }
      const data = await res.json();
      setActiveGoals(data.goals || []);
    } catch {
      // silent - non-critical
    }
  }, []);

  const handleGoalAction = useCallback(
    async (sessionId: string, action: GoalPanelAction) => {
      if (outSessionIds.current.has(sessionId)) {
        return;
      }
      outSessionIds.current.add(sessionId);
      setPendingSessionIds(new Set(outSessionIds.current));
      try {
        const outcome = await postGoalAction(sessionId, action);
        if (outcome === 'done') {
          toast.success(t('goalActionSuccess'));
          await fetchActiveGoals();
        } else if (outcome === 'busy') {
          toast.error(tGoal('goalActionBusy'));
        } else if (outcome === 'failed') {
          toast.error(tGoal(`goalActionFailed_${action}`));
        }
      } finally {
        outSessionIds.current.delete(sessionId);
        setPendingSessionIds(new Set(outSessionIds.current));
      }
    },
    [fetchActiveGoals, t, tGoal],
  );

  return { activeGoals, fetchActiveGoals, pendingSessionIds, handleGoalAction };
}
