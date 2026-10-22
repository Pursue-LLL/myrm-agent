import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { GoalStatusHeader } from '../GoalStatusHeader';
import type { GoalState } from '../goalStatusTypes';

vi.mock('@/components/features/checkpoint/TaskAirbagCapsule', () => ({ TaskAirbagCapsule: () => null }));

const t = ((key: string) => key) as ComponentProps<typeof GoalStatusHeader>['t'];

function renderHeader(status: GoalState['status'], overrides: Partial<ComponentProps<typeof GoalStatusHeader>> = {}) {
  const onPause = vi.fn();
  const onAction = vi.fn();
  const goal: GoalState = { goalId: 'g1', objective: 'Ship it', status, tokensUsed: 0, timeUsedSeconds: 0 };
  render(
    <GoalStatusHeader
      goal={goal}
      gitBranch={null}
      isTerminal={status === 'complete' || status === 'cancelled'}
      isWarning={false}
      isCritical={false}
      etaSeconds={null}
      hasSufficientData
      displayReason={undefined}
      queueCount={0}
      onToggleExpand={vi.fn()}
      onPause={onPause}
      onAction={onAction}
      t={t}
      {...overrides}
    />,
  );
  return { onPause, onAction };
}

describe('GoalStatusHeader pause control', () => {
  it('lets the user pause a goal that is waiting for its usage limit to reset', () => {
    const { onPause, onAction } = renderHeader('wait');

    const trigger = screen.getByTestId('goal-pause-trigger');
    expect(trigger.getAttribute('aria-label')).toBe('pauseDialogTitle');
    fireEvent.click(trigger);

    expect(onPause).toHaveBeenCalledTimes(1);
    expect(onAction).not.toHaveBeenCalled();
  });

  it('names every icon-only action of a waiting goal', () => {
    const { onAction } = renderHeader('wait');

    fireEvent.click(screen.getByRole('button', { name: 'usageLimitResume' }));
    fireEvent.click(screen.getByRole('button', { name: 'cancel' }));

    expect(onAction.mock.calls).toEqual([['unwait'], ['cancel']]);
  });

  it('keeps the pause control for an active goal', () => {
    renderHeader('active');

    expect(screen.getByTestId('goal-pause-trigger')).toBeTruthy();
  });

  it('offers resume instead of pause once the goal is paused', () => {
    renderHeader('paused');

    expect(screen.queryByTestId('goal-pause-trigger')).toBeNull();
  });

  it('hides every control for a finished goal', () => {
    renderHeader('complete');

    expect(screen.queryByTestId('goal-pause-trigger')).toBeNull();
  });
});
