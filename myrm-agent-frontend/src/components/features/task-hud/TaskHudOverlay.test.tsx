/**
 * Unit & Integration tests for TaskHudOverlay component.
 *
 * [INPUT] TaskHudOverlay component, useTaskHudStore
 * [OUTPUT] Vitest test suite verifying overlay rendering, progress bar, expansion, and status toggle.
 * [POS] Item 31 unit tests. Strictly under 160 lines. Zero `any`.
 */

import React from 'react';
import { describe, it, expect, beforeEach } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import { TaskHudOverlay } from './TaskHudOverlay';
import { useTaskHudStore } from '@/store/useTaskHudStore';
import type { TaskItem } from './taskHudTypes';

describe('TaskHudOverlay', () => {
  beforeEach(() => {
    act(() => {
      useTaskHudStore.getState().setTasks([]);
      useTaskHudStore.getState().setExpanded(false);
    });
  });

  const mockTasks: TaskItem[] = [
    {
      id: 'step_1',
      title: 'Analyze database schema',
      status: 'completed',
      progress_percent: 100,
      details: 'Check index coverage and migration files',
      created_at: '2026-08-31T00:00:00Z',
      updated_at: '2026-08-31T00:00:00Z',
    },
    {
      id: 'step_2',
      title: 'Implement anti-compaction engine',
      status: 'in_progress',
      progress_percent: 40,
      details: 'Maintain state-isolated session machine',
      created_at: '2026-08-31T00:00:00Z',
      updated_at: '2026-08-31T00:00:00Z',
    },
  ];

  it('renders nothing when tasks list is empty', () => {
    const { container } = render(<TaskHudOverlay />);
    expect(container.firstChild).toBeNull();
  });

  it('renders active task title, anti-compaction badge, and overall progress', () => {
    act(() => {
      useTaskHudStore.getState().setTasks(mockTasks);
    });

    render(<TaskHudOverlay />);

    expect(screen.getByText('Implement anti-compaction engine')).toBeInTheDocument();
    expect(screen.getByText('抗压缩')).toBeInTheDocument();
    // Overall progress: (100 + 40) / 2 = 70%
    expect(screen.getByText(/70% \(1\/2\)/)).toBeInTheDocument();
  });

  it('toggles checklist expansion when expand button is clicked', () => {
    act(() => {
      useTaskHudStore.getState().setTasks(mockTasks);
    });

    render(<TaskHudOverlay />);

    expect(screen.queryByText(/Check index coverage and migration files/)).not.toBeInTheDocument();

    const expandBtn = screen.getByRole('button', { name: /展开任务清单/ });
    fireEvent.click(expandBtn);

    expect(screen.getByText(/Check index coverage and migration files/)).toBeInTheDocument();
    expect(screen.getByText(/Maintain state-isolated session machine/)).toBeInTheDocument();
  });

  it('allows in-place status toggle via checklist item icon', () => {
    act(() => {
      useTaskHudStore.getState().setTasks(mockTasks);
      useTaskHudStore.getState().setExpanded(true);
    });

    render(<TaskHudOverlay />);

    const toggleStep2Btn = screen.getByRole('button', {
      name: /切换任务 Implement anti-compaction engine 状态/,
    });
    fireEvent.click(toggleStep2Btn);

    // in_progress toggled should mark as completed (100%)
    const state = useTaskHudStore.getState();
    const step2 = state.tasks.find((t) => t.id === 'step_2');
    expect(step2?.status).toBe('completed');
    expect(step2?.progress_percent).toBe(100);
  });
});
