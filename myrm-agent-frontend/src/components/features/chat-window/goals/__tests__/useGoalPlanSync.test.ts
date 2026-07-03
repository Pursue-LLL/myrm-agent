import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useGoalPlanSync } from '../useGoalPlanSync';
import { usePlanStore } from '@/store/chat/goals/usePlanStore';

vi.mock('@/store/useChatStore', () => ({
  default: {
    getState: vi.fn(() => ({ loading: false })),
  },
}));

const makePlan = () => ({
  goal: 'Test',
  reasoning: '',
  steps: [{ step_id: 'a', description: 'Step A', status: 'pending' as const, expected_output: '', dependencies: [] }],
});

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
    renderHook(() => useGoalPlanSync('chat-1'));

    act(() => {
      usePlanStore.setState({ plan: makePlan() });
    });

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
    renderHook(() => useGoalPlanSync('chat-1'));

    act(() => {
      usePlanStore.setState({ plan: makePlan() });
    });

    act(() => {
      window.dispatchEvent(
        new CustomEvent('tasks_steps', {
          detail: { chat_id: 'other', type: 'tasks_steps', step_key: 'todo_step_a', status: 'success' },
        }),
      );
    });

    expect(usePlanStore.getState().plan?.steps[0].status).toBe('pending');
  });

  it('clears plan on chatId change', () => {
    const { rerender } = renderHook(({ id }) => useGoalPlanSync(id), {
      initialProps: { id: 'chat-1' as string | null },
    });

    act(() => {
      usePlanStore.setState({ plan: makePlan() });
    });
    expect(usePlanStore.getState().plan).not.toBeNull();

    rerender({ id: 'chat-2' });
    expect(usePlanStore.getState().plan).toBeNull();
  });

  it('clears plan when chatId becomes null', () => {
    const { rerender } = renderHook(({ id }) => useGoalPlanSync(id), {
      initialProps: { id: 'chat-1' as string | null },
    });

    act(() => {
      usePlanStore.setState({ plan: makePlan() });
    });

    rerender({ id: null });
    expect(usePlanStore.getState().plan).toBeNull();
  });

  it('clears active plan on multiplex_reconnected when not loading', () => {
    renderHook(() => useGoalPlanSync('chat-1'));

    act(() => {
      usePlanStore.setState({ plan: makePlan() });
    });

    act(() => {
      window.dispatchEvent(new CustomEvent('multiplex_reconnected'));
    });

    expect(usePlanStore.getState().plan).toBeNull();
  });

  it('does NOT clear active plan on multiplex_reconnected when loading', async () => {
    const useChatStore = await import('@/store/useChatStore');
    (useChatStore.default.getState as ReturnType<typeof vi.fn>).mockReturnValue({ loading: true });

    renderHook(() => useGoalPlanSync('chat-1'));

    act(() => {
      usePlanStore.setState({ plan: makePlan() });
    });

    act(() => {
      window.dispatchEvent(new CustomEvent('multiplex_reconnected'));
    });

    expect(usePlanStore.getState().plan).not.toBeNull();
    (useChatStore.default.getState as ReturnType<typeof vi.fn>).mockReturnValue({ loading: false });
  });

  it('refetches plan on progress_root event', () => {
    const mockFetchPlan = vi.fn().mockResolvedValue(undefined);
    usePlanStore.setState({ fetchPlan: mockFetchPlan });

    renderHook(() => useGoalPlanSync('chat-1'));
    mockFetchPlan.mockClear();

    act(() => {
      window.dispatchEvent(
        new CustomEvent('tasks_steps', {
          detail: { chat_id: 'chat-1', type: 'tasks_steps', step_key: 'progress_root', status: 'running' },
        }),
      );
    });

    expect(mockFetchPlan).toHaveBeenCalledWith('chat-1');
  });

  it('maps running status to in_progress', () => {
    renderHook(() => useGoalPlanSync('chat-1'));

    act(() => {
      usePlanStore.setState({ plan: makePlan() });
    });

    act(() => {
      window.dispatchEvent(
        new CustomEvent('tasks_steps', {
          detail: { chat_id: 'chat-1', type: 'tasks_steps', step_key: 'todo_step_a', status: 'running' },
        }),
      );
    });

    expect(usePlanStore.getState().plan?.steps[0].status).toBe('in_progress');
  });

  it('maps skipped status correctly', () => {
    renderHook(() => useGoalPlanSync('chat-1'));

    act(() => {
      usePlanStore.setState({ plan: makePlan() });
    });

    act(() => {
      window.dispatchEvent(
        new CustomEvent('tasks_steps', {
          detail: { chat_id: 'chat-1', type: 'tasks_steps', step_key: 'todo_step_a', status: 'skipped' },
        }),
      );
    });

    expect(usePlanStore.getState().plan?.steps[0].status).toBe('skipped');
  });

  it('maps unknown status to pending', () => {
    renderHook(() => useGoalPlanSync('chat-1'));

    act(() => {
      usePlanStore.setState({ plan: makePlan() });
    });

    act(() => {
      window.dispatchEvent(
        new CustomEvent('tasks_steps', {
          detail: { chat_id: 'chat-1', type: 'tasks_steps', step_key: 'todo_step_a', status: 'unknown_value' },
        }),
      );
    });

    expect(usePlanStore.getState().plan?.steps[0].status).toBe('pending');
  });

  it('removes event listeners on unmount', () => {
    const removeSpy = vi.spyOn(window, 'removeEventListener');
    const { unmount } = renderHook(() => useGoalPlanSync('chat-1'));

    unmount();

    const removedEvents = removeSpy.mock.calls.map((c) => c[0]);
    expect(removedEvents).toContain('tasks_steps');
    expect(removedEvents).toContain('multiplex_reconnected');
    removeSpy.mockRestore();
  });
});
