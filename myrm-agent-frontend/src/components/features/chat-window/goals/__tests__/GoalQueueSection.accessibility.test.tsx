import { act, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import { expectDefined } from '@/test-utils/expectDefined';
import { GoalQueueSection } from '../GoalQueueSection';

vi.mock('next-intl', async () => (await import('@/test-utils/realIntl')).createRealIntlMock(() => 'zh'));

describe('GoalQueueSection keyboard reordering', () => {
  it('names the grip and announces the goal objective instead of the goal id', async () => {
    const user = userEvent.setup();
    useGoalStore.setState({
      queuedGoals: [
        { goal_id: 'goal-5d2e', objective: '整理本周发布清单', priority: 0, status: 'queued' },
        { goal_id: 'goal-8b41', objective: '回归测试', priority: 0, status: 'queued' },
      ],
    });
    render(<GoalQueueSection />);

    const [grip] = screen.getAllByRole('button', { name: '拖动调整顺序' });
    expectDefined(grip, 'first grip');
    expect(grip).toHaveAttribute('aria-roledescription', '可拖动项');

    await act(async () => grip.focus());
    await user.keyboard(' ');

    const liveRegion = screen.getByRole('status');
    expect(liveRegion).toHaveTextContent('已拾起“整理本周发布清单”。');
    expect(liveRegion).not.toHaveTextContent('goal-5d2e');
  });
});
