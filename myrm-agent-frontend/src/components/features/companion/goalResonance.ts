import type { GoalStatus } from '@/components/features/chat-window/goals/goalStatusTypes';

export interface GoalSnapshot {
  goalId: string;
  status: GoalStatus;
}

export type GoalResonance = 'paused' | 'complete' | 'resumed';

/**
 * What the companion reacts to between two observations of the active goal.
 *
 * Only a status change of one and the same goal is something that happened to it. A goal that appears, disappears or is
 * replaced (opening a chat, loading its goal, a new goal) is not a transition, so a goal that was already complete is
 * never celebrated again.
 */
export function resolveGoalResonance(prev: GoalSnapshot | null, next: GoalSnapshot | null): GoalResonance | null {
  if (!prev || !next || prev.goalId !== next.goalId || prev.status === next.status) {
    return null;
  }
  if (next.status === 'paused') {
    return 'paused';
  }
  if (next.status === 'complete') {
    return 'complete';
  }
  if (next.status === 'active' && prev.status === 'paused') {
    return 'resumed';
  }
  return null;
}
