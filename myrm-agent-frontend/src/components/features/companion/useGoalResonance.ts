'use client';

import { useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';

import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import useCompanionStore from '@/store/useCompanionStore';

import { resolveGoalResonance } from './goalResonance';

import type { GoalResonance, GoalSnapshot } from './goalResonance';

const MESSAGE_KEYS = {
  paused: 'statusPaused',
  complete: 'statusComplete',
  resumed: 'statusActive',
} as const satisfies Record<GoalResonance, string>;

const CELEBRATION_MS = 600;

/**
 * The companion's reaction to what happens to the active goal: a speech bubble for a pause, a completion or a resume,
 * and a bounce when the goal completes. Only a status change of one goal counts; a goal that is loaded into view or
 * replaced by another one is not something that just happened.
 */
export function useGoalResonance(setAnimState: (state: 'idle' | 'bounce') => void): void {
  const tGoal = useTranslations('Goal');
  const goalId = useGoalStore((s) => s.activeGoal?.goalId);
  const goalStatus = useGoalStore((s) => s.activeGoal?.status);
  const prevGoalRef = useRef<GoalSnapshot | null>(goalId && goalStatus ? { goalId, status: goalStatus } : null);

  useEffect(() => {
    const next: GoalSnapshot | null = goalId && goalStatus ? { goalId, status: goalStatus } : null;
    const resonance = resolveGoalResonance(prevGoalRef.current, next);
    prevGoalRef.current = next;
    if (!resonance) {
      return;
    }

    useCompanionStore.getState().setReaction(tGoal(MESSAGE_KEYS[resonance]));
    if (resonance !== 'complete') {
      return;
    }
    setAnimState('bounce');
    const timer = setTimeout(() => setAnimState('idle'), CELEBRATION_MS);
    return () => clearTimeout(timer);
  }, [goalId, goalStatus, tGoal, setAnimState]);
}
