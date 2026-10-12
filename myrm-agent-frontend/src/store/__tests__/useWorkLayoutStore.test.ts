/** @vitest-environment jsdom */
import { beforeEach, describe, expect, it } from 'vitest';
import { useWorkLayoutStore } from '../useWorkLayoutStore';

describe('useWorkLayoutStore', () => {
  beforeEach(() => {
    useWorkLayoutStore.setState({
      viewMode: 'chat',
      computeTier: 'turbo',
      workSidebarTab: 'tasks',
      isSidebarCollapsed: false,
      activeTaskId: 'task-1',
    });
  });

  it('initializes with expected default values', () => {
    const state = useWorkLayoutStore.getState();
    expect(state.viewMode).toBe('chat');
    expect(state.computeTier).toBe('turbo');
    expect(state.workSidebarTab).toBe('tasks');
    expect(state.isSidebarCollapsed).toBe(false);
    expect(state.tasks.length).toBeGreaterThan(0);
  });

  it('updates viewMode via setViewMode and toggleViewMode', () => {
    const { setViewMode, toggleViewMode } = useWorkLayoutStore.getState();

    setViewMode('work');
    expect(useWorkLayoutStore.getState().viewMode).toBe('work');

    toggleViewMode();
    expect(useWorkLayoutStore.getState().viewMode).toBe('chat');

    toggleViewMode();
    expect(useWorkLayoutStore.getState().viewMode).toBe('work');
  });

  it('updates computeTier via setComputeTier and toggleComputeTier', () => {
    const { setComputeTier, toggleComputeTier } = useWorkLayoutStore.getState();

    setComputeTier('pro');
    expect(useWorkLayoutStore.getState().computeTier).toBe('pro');

    toggleComputeTier();
    expect(useWorkLayoutStore.getState().computeTier).toBe('turbo');
  });

  it('updates workSidebarTab and sidebar collapsed states', () => {
    const { setWorkSidebarTab, toggleSidebarCollapsed, setSidebarCollapsed } =
      useWorkLayoutStore.getState();

    setWorkSidebarTab('skills');
    expect(useWorkLayoutStore.getState().workSidebarTab).toBe('skills');

    toggleSidebarCollapsed();
    expect(useWorkLayoutStore.getState().isSidebarCollapsed).toBe(true);

    setSidebarCollapsed(false);
    expect(useWorkLayoutStore.getState().isSidebarCollapsed).toBe(false);
  });

  it('updates task status and calculates subtask completion progress', () => {
    const { updateTaskStatus, toggleSubtask } = useWorkLayoutStore.getState();

    updateTaskStatus('task-1', 'in_progress', 50);
    const updated = useWorkLayoutStore.getState().tasks.find((t) => t.id === 'task-1');
    expect(updated?.status).toBe('in_progress');
    expect(updated?.progressPercentage).toBe(50);

    // Toggle subtask in task-1
    toggleSubtask('task-1', 'sub-1');
    const afterSubtask = useWorkLayoutStore.getState().tasks.find((t) => t.id === 'task-1');
    // sub-1 was completed (true), toggled to false, so progress becomes 50%
    expect(afterSubtask?.subtasks[0].completed).toBe(false);
    expect(afterSubtask?.progressPercentage).toBe(50);
  });
});
