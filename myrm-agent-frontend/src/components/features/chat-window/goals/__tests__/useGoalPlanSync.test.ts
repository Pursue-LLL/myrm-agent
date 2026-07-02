import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useGoalPlanSync } from '../useGoalPlanSync';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';

describe('useGoalPlanSync', () => {
  beforeEach(() => {
    usePlanStore.setState({
      plan: null,
      isLoading: false,
      fetchPlan: vi.fn().mockResolvedValue(undefined),
    });
    vi.restoreAllMocks();
  });

  it('updates step status from todo_step SSE events', () => {
    usePlanStore.setState({
      plan: {
        goal: 'Test',
        reasoning: '',
        steps: [{ step_id: 'a', description: 'Step A', status: 'pending', expected_output: '', dependencies: [] }],
      },
    });

    renderHook(() => useGoalPlanSync('chat-1'));

    act(() => {
      window.dispatchEvent(
        new CustomEvent('tasks_steps', {
          detail: { chat_id: 'chat-1', type: 'tasks_steps', step_key: 'todo_step_a', status: 'success' },
        }),
      );
    });

    expect(usePlanStore.getState().plan?.steps[0].status).toBe('completed');
  });

  it('ignores SSE events for other chats', () => {
    usePlanStore.setState({
      plan: {
        goal: 'Test',
        reasoning: '',
        steps: [{ step_id: 'a', description: 'Step A', status: 'pending', expected_output: '', dependencies: [] }],
      },
    });

    renderHook(() => useGoalPlanSync('chat-1'));

    act(() => {
      window.dispatchEvent(
        new CustomEvent('tasks_steps', {
          detail: { chat_id: 'other', type: 'tasks_steps', step_key: 'todo_step_a', status: 'success' },
        }),
      );
    });

    expect(usePlanStore.getState().plan?.steps[0].status).toBe('pending');
  });
});
