import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { normalizeGoalState } from '@/store/chat/messageStream/streamHelpers';
import type { GoalStatusPayload } from '@/store/chat/types';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { GoalUsageLimitRow } from '../GoalUsageLimitRow';
import { formatResumeTime, translateGoalReason } from '../goalStatusUtils';

const NOW = new Date('2026-10-13T10:00:00');

function payload(overrides: Partial<GoalStatusPayload>): GoalStatusPayload {
  return {
    goal_id: 'g1',
    objective: 'Ship it',
    status: 'wait',
    tokens_used: 0,
    time_used_seconds: 0,
    ...overrides,
  };
}

describe('formatResumeTime', () => {
  it('shows only the clock time for a same-day instant', () => {
    const text = formatResumeTime('2026-10-13T15:42:00', 'en', NOW);
    expect(text).toMatch(/3:42/);
    expect(text).not.toMatch(/Oct/);
  });

  it('adds the date when the instant is not today', () => {
    const text = formatResumeTime('2026-10-14T03:05:00', 'en', NOW);
    expect(text).toMatch(/Oct/);
    expect(text).toMatch(/14/);
    expect(text).toMatch(/3:05/);
  });

  it('returns undefined for missing or invalid input', () => {
    expect(formatResumeTime(undefined, 'en', NOW)).toBeUndefined();
    expect(formatResumeTime('not-a-date', 'en', NOW)).toBeUndefined();
  });
});

describe('translateGoalReason usage-limit reasons', () => {
  it('maps both provider-window reasons to the localized label', () => {
    const t = (key: string) => `t:${key}`;
    expect(translateGoalReason('Provider usage limit reached; resuming automatically', t)).toBe('t:reasonUsageLimit');
    expect(translateGoalReason('Provider usage limit reached; paused until it resets', t)).toBe('t:reasonUsageLimit');
  });
});

describe('normalizeGoalState usageLimit', () => {
  it('reads a WAIT hold with its resume boundary', () => {
    const goal = normalizeGoalState(
      payload({ status: 'wait', metadata: { wait_kind: 'usage_limit', wait_resume_at: '2026-10-13T15:42:00+00:00' } }),
    );
    expect(goal.usageLimit).toEqual({ resumeAt: '2026-10-13T15:42:00+00:00' });
  });

  it('reads a PAUSED hold through pause_kind', () => {
    const goal = normalizeGoalState(
      payload({
        status: 'paused',
        metadata: { pause_kind: 'usage_limit', wait_resume_at: '2026-10-20T00:00:00+00:00' },
      }),
    );
    expect(goal.usageLimit).toEqual({ resumeAt: '2026-10-20T00:00:00+00:00' });
  });

  it('keeps the hold but drops an empty boundary', () => {
    const goal = normalizeGoalState(
      payload({ status: 'paused', metadata: { pause_kind: 'usage_limit', wait_resume_at: '' } }),
    );
    expect(goal.usageLimit).toEqual({ resumeAt: undefined });
  });

  it('ignores other waits and holds from a stale status', () => {
    expect(normalizeGoalState(payload({ status: 'wait', metadata: {} })).usageLimit).toBeUndefined();
    expect(
      normalizeGoalState(
        payload({ status: 'active', metadata: { wait_kind: 'usage_limit', pause_kind: 'usage_limit' } }),
      ).usageLimit,
    ).toBeUndefined();
  });
});

describe('useGoalStore.updateGoalStatus', () => {
  it('drops the usage-limit hold when the user changes the status', () => {
    useGoalStore
      .getState()
      .setActiveGoal(
        '',
        normalizeGoalState(
          payload({ status: 'wait', metadata: { wait_kind: 'usage_limit', wait_resume_at: '2026-10-13T15:42:00Z' } }),
        ),
      );
    useGoalStore.getState().updateGoalStatus('', 'active');
    expect(useGoalStore.getState().activeGoal?.usageLimit).toBeUndefined();
  });
});

describe('GoalUsageLimitRow', () => {
  const onAction = vi.fn<(action: string) => Promise<void>>();

  beforeEach(() => {
    onAction.mockReset();
    onAction.mockResolvedValue(undefined);
  });

  it('offers an immediate retry while the goal waits for the reset', async () => {
    render(<GoalUsageLimitRow status="wait" resumeAt="2026-10-13T15:42:00" onAction={onAction} />);

    expect(screen.getByText('usageLimitWaiting')).toBeTruthy();
    fireEvent.click(screen.getByTestId('goal-usage-limit-action'));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith('unwait'));
  });

  it('offers resume when the goal is paused by the limit', async () => {
    render(<GoalUsageLimitRow status="paused" resumeAt={undefined} onAction={onAction} />);

    expect(screen.getByText('usageLimitPausedNoTime')).toBeTruthy();
    fireEvent.click(screen.getByTestId('goal-usage-limit-action'));
    await waitFor(() => expect(onAction).toHaveBeenCalledWith('resume'));
  });

  it('disables the action while a request is in flight', async () => {
    let finish: () => void = () => {};
    onAction.mockReturnValue(new Promise<void>((resolve) => (finish = resolve)));
    render(<GoalUsageLimitRow status="wait" resumeAt={undefined} onAction={onAction} />);

    const button = screen.getByTestId('goal-usage-limit-action') as HTMLButtonElement;
    fireEvent.click(button);
    await waitFor(() => expect(button.disabled).toBe(true));
    finish();
    await waitFor(() => expect(button.disabled).toBe(false));
    expect(onAction).toHaveBeenCalledTimes(1);
  });
});
