/**
 * Unit tests for useTaskHudStore.
 *
 * [INPUT] useTaskHudStore, mock TaskItems
 * [OUTPUT] Vitest test suite verifying task additions, status updates, and progress calculations.
 * [POS] Item 31 unit tests. Strictly under 150 lines. Zero `any`.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { act } from '@testing-library/react';
import { useTaskHudStore } from '@/store/useTaskHudStore';
import type { TaskItem } from './taskHudTypes';

describe('useTaskHudStore', () => {
  beforeEach(() => {
    act(() => {
      useTaskHudStore.getState().setTasks([]);
      useTaskHudStore.getState().setExpanded(false);
    });
  });

  const task1: TaskItem = {
    id: 'step_1',
    title: 'Initialize workspace',
    status: 'pending',
    progress_percent: 0,
    created_at: '2026-08-31T00:00:00Z',
    updated_at: '2026-08-31T00:00:00Z',
  };

  const task2: TaskItem = {
    id: 'step_2',
    title: 'Compile assets',
    status: 'pending',
    progress_percent: 0,
    created_at: '2026-08-31T00:00:00Z',
    updated_at: '2026-08-31T00:00:00Z',
  };

  it('initializes with empty tasks and zero progress', () => {
    const state = useTaskHudStore.getState();
    expect(state.tasks).toEqual([]);
    expect(state.overallProgress).toBe(0);
    expect(state.activeTaskId).toBeNull();
    expect(state.isExpanded).toBe(false);
  });

  it('adds and calculates progress correctly', () => {
    act(() => {
      useTaskHudStore.getState().addTask(task1);
      useTaskHudStore.getState().addTask(task2);
    });

    let state = useTaskHudStore.getState();
    expect(state.tasks.length).toBe(2);
    expect(state.overallProgress).toBe(0);
    expect(state.activeTaskId).toBe('step_1');

    // Update step 1 to in_progress (default 50%)
    act(() => {
      useTaskHudStore.getState().updateTaskStatus('step_1', 'in_progress');
    });

    state = useTaskHudStore.getState();
    expect(state.overallProgress).toBe(25); // (50 + 0) / 2 = 25%

    // Update step 1 to completed (100%)
    act(() => {
      useTaskHudStore.getState().updateTaskStatus('step_1', 'completed');
    });

    state = useTaskHudStore.getState();
    expect(state.overallProgress).toBe(50); // (100 + 0) / 2 = 50%
    expect(state.activeTaskId).toBe('step_2');
  });

  it('supports task removal', () => {
    act(() => {
      useTaskHudStore.getState().setTasks([task1, task2]);
    });

    expect(useTaskHudStore.getState().tasks.length).toBe(2);

    act(() => {
      useTaskHudStore.getState().removeTask('step_2');
    });

    expect(useTaskHudStore.getState().tasks.length).toBe(1);
    expect(useTaskHudStore.getState().tasks[0].id).toBe('step_1');
  });

  it('toggles expansion state', () => {
    expect(useTaskHudStore.getState().isExpanded).toBe(false);

    act(() => {
      useTaskHudStore.getState().toggleExpanded();
    });
    expect(useTaskHudStore.getState().isExpanded).toBe(true);

    act(() => {
      useTaskHudStore.getState().toggleExpanded();
    });
    expect(useTaskHudStore.getState().isExpanded).toBe(false);
  });
});
