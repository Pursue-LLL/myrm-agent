import { resolveGoalResonance } from '../goalResonance';

import type { GoalStatus } from '@/components/features/chat-window/goals/goalStatusTypes';

const goal = (goalId: string, status: GoalStatus) => ({ goalId, status });

describe('resolveGoalResonance', () => {
  it('reacts to the status changes of one goal', () => {
    expect(resolveGoalResonance(goal('g1', 'active'), goal('g1', 'paused'))).toBe('paused');
    expect(resolveGoalResonance(goal('g1', 'active'), goal('g1', 'complete'))).toBe('complete');
    expect(resolveGoalResonance(goal('g1', 'paused'), goal('g1', 'active'))).toBe('resumed');
  });

  it('stays quiet for changes that are not worth a reaction', () => {
    expect(resolveGoalResonance(goal('g1', 'active'), goal('g1', 'active'))).toBeNull();
    expect(resolveGoalResonance(goal('g1', 'complete'), goal('g1', 'complete'))).toBeNull();
    expect(resolveGoalResonance(goal('g1', 'queued'), goal('g1', 'active'))).toBeNull();
    expect(resolveGoalResonance(goal('g1', 'active'), goal('g1', 'cancelled'))).toBeNull();
  });

  it('does not celebrate a goal that was already complete when it showed up', () => {
    expect(resolveGoalResonance(null, goal('g1', 'complete'))).toBeNull();
    expect(resolveGoalResonance(null, goal('g1', 'paused'))).toBeNull();
  });

  it('does not react to a goal that is replaced by another one', () => {
    expect(resolveGoalResonance(goal('g1', 'active'), goal('g2', 'complete'))).toBeNull();
    expect(resolveGoalResonance(goal('g1', 'active'), goal('g2', 'paused'))).toBeNull();
    expect(resolveGoalResonance(goal('g1', 'paused'), goal('g2', 'active'))).toBeNull();
  });

  it('does not react when the goal disappears', () => {
    expect(resolveGoalResonance(goal('g1', 'complete'), null)).toBeNull();
    expect(resolveGoalResonance(null, null)).toBeNull();
  });
});
