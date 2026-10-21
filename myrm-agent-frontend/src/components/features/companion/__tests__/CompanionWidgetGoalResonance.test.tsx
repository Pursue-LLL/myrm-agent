// @vitest-environment jsdom
/**
 * Real scenario: the user finished a goal in chat A, then opens chat B whose goal was completed yesterday. The companion
 * celebrates the goal that just finished in front of the user, not a goal that merely got loaded into view.
 */
import { act, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/store/useAuthStore', () => ({
  default: (selector: (state: { user: { id: string } }) => unknown) => selector({ user: { id: 'user-1' } }),
}));
vi.mock('../CompanionBubble', () => ({ default: () => null }));
vi.mock('../CompanionSprite', () => ({
  default: ({ animState }: { animState: string }) => <span data-testid="sprite" data-anim={animState} />,
}));
vi.mock('../CompanionSettings', () => ({ default: () => null }));

import useCompanionStore from '@/store/useCompanionStore';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import CompanionWidget from '../CompanionWidget';

import type { GoalState, GoalStatus } from '@/components/features/chat-window/goals/goalStatusTypes';

const goal = (goalId: string, status: GoalStatus): GoalState => ({
  goalId,
  objective: goalId,
  status,
  tokensUsed: 0,
  timeUsedSeconds: 0,
});

const reaction = () => useCompanionStore.getState().currentReaction;
const spriteAnim = () => screen.getByTestId('sprite').dataset.anim;

describe('CompanionWidget goal resonance', () => {
  beforeEach(() => {
    useCompanionStore.setState({ enabled: true, hatchedAt: Date.now(), currentReaction: null });
    useGoalStore.setState({ chatId: null, activeGoal: null, gitBranch: null, queuedGoals: [] });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('celebrates the goal of the open chat that has just completed', () => {
    useGoalStore.getState().bindChat('chat-a');
    useGoalStore.getState().setActiveGoal('chat-a', goal('goal-a', 'active'));
    render(<CompanionWidget />);

    act(() => useGoalStore.getState().updateGoalStatus('chat-a', 'complete'));

    expect(reaction()).toBe('statusComplete');
  });

  it('reacts when the goal of the open chat is paused and then resumed', () => {
    useGoalStore.getState().bindChat('chat-a');
    useGoalStore.getState().setActiveGoal('chat-a', goal('goal-a', 'active'));
    render(<CompanionWidget />);

    act(() => useGoalStore.getState().updateGoalStatus('chat-a', 'paused'));
    expect(reaction()).toBe('statusPaused');

    act(() => useGoalStore.getState().updateGoalStatus('chat-a', 'active'));
    expect(reaction()).toBe('statusActive');
  });

  it('does not celebrate a goal that was already complete in the chat that is opened', () => {
    useGoalStore.getState().bindChat('chat-a');
    useGoalStore.getState().setActiveGoal('chat-a', goal('goal-a', 'active'));
    render(<CompanionWidget />);

    act(() => {
      useGoalStore.getState().bindChat('chat-b');
      useGoalStore.getState().setActiveGoal('chat-b', goal('goal-b', 'complete'));
    });

    expect(reaction()).toBeNull();
  });

  it('stops bouncing after the celebration even when another chat is opened meanwhile', () => {
    vi.useFakeTimers();
    useGoalStore.getState().bindChat('chat-a');
    useGoalStore.getState().setActiveGoal('chat-a', goal('goal-a', 'active'));
    render(<CompanionWidget />);

    act(() => useGoalStore.getState().updateGoalStatus('chat-a', 'complete'));
    expect(spriteAnim()).toBe('bounce');

    act(() => useGoalStore.getState().bindChat('chat-b'));
    act(() => {
      vi.advanceTimersByTime(1000);
    });

    expect(spriteAnim()).toBe('idle');
  });

  it('does not celebrate a completed goal that finishes loading after the widget is shown', () => {
    render(<CompanionWidget />);

    act(() => {
      useGoalStore.getState().bindChat('chat-a');
      useGoalStore.getState().setActiveGoal('chat-a', goal('goal-a', 'complete'));
    });

    expect(reaction()).toBeNull();
  });
});
