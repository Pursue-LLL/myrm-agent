import React from 'react';
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { TaskExecutionTimelineDrawer } from '../TaskExecutionTimelineDrawer';
import { useTaskInspectorStore } from '../useTaskInspectorStore';
import type { TaskTimelineData } from '../taskInspectorTypes';

describe('TaskExecutionTimelineDrawer', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    useTaskInspectorStore.setState({
      isOpen: false,
      activeTaskId: null,
      viewMode: 'tree',
      timelineData: null,
      isLoading: false,
      isInterrupting: false,
      selectedNodeId: null,
      expandedNodeIds: [],
      error: null,
    });
  });

  const mockTimelineData: TaskTimelineData = {
    task_id: 'task_exec_999',
    tree: [
      {
        node_id: 'node_root',
        step_name: 'DecomposeTask',
        parent_id: null,
        step_index: 1,
        node_type: 'agent_thought',
        status: 'completed',
        start_time_ms: 1000,
        end_time_ms: 1200,
        duration_ms: 200,
        input_payload: { goal: 'build search index' },
        output_payload: { status: 'subtasks generated' },
        metrics: {
          input_chars: 120,
          output_chars: 300,
          prompt_tokens: 45,
          completion_tokens: 90,
          cache_hit: true,
        },
        error_message: null,
        children: [
          {
            node_id: 'node_child_1',
            step_name: 'ExtractTokens',
            parent_id: 'node_root',
            step_index: 2,
            node_type: 'tool_invocation',
            status: 'running',
            start_time_ms: 1205,
            end_time_ms: null,
            duration_ms: null,
            input_payload: { batch: '1' },
            output_payload: null,
            metrics: {
              input_chars: 50,
              output_chars: 0,
              prompt_tokens: 20,
              completion_tokens: 0,
              cache_hit: false,
            },
            error_message: null,
            children: [],
          },
        ],
      },
    ],
    waterfall: [
      {
        node_id: 'node_root',
        step_name: 'DecomposeTask',
        parent_id: null,
        step_index: 1,
        node_type: 'agent_thought',
        status: 'completed',
        start_time_ms: 1000,
        end_time_ms: 1200,
        duration_ms: 200,
        input_payload: { goal: 'build search index' },
        output_payload: { status: 'subtasks generated' },
        metrics: {
          input_chars: 120,
          output_chars: 300,
          prompt_tokens: 45,
          completion_tokens: 90,
          cache_hit: true,
        },
        error_message: null,
        children: [],
      },
      {
        node_id: 'node_child_1',
        step_name: 'ExtractTokens',
        parent_id: 'node_root',
        step_index: 2,
        node_type: 'tool_invocation',
        status: 'running',
        start_time_ms: 1205,
        end_time_ms: null,
        duration_ms: null,
        input_payload: { batch: '1' },
        output_payload: null,
        metrics: {
          input_chars: 50,
          output_chars: 0,
          prompt_tokens: 20,
          completion_tokens: 0,
          cache_hit: false,
        },
        error_message: null,
        children: [],
      },
    ],
    summary: {
      total_steps: 2,
      completed_steps: 1,
      failed_steps: 0,
      running_steps: 1,
      interrupted_steps: 0,
      total_duration_ms: 200,
      total_tokens: 155,
    },
    interruptions: [],
  };

  it('renders nothing when isOpen is false', () => {
    const { container } = render(<TaskExecutionTimelineDrawer />);
    expect(container.firstChild).toBeNull();
  });

  it('renders drawer header, metrics and steps when open', () => {
    useTaskInspectorStore.setState({
      isOpen: true,
      activeTaskId: 'task_exec_999',
      timelineData: mockTimelineData,
    });

    render(<TaskExecutionTimelineDrawer />);

    expect(screen.getByText('task_exec_999')).toBeInTheDocument();
    expect(screen.getByText('DecomposeTask')).toBeInTheDocument();
    expect(screen.getByText(/200ms/)).toBeInTheDocument();
  });

  it('switches between tree and waterfall view modes', () => {
    useTaskInspectorStore.setState({
      isOpen: true,
      activeTaskId: 'task_exec_999',
      timelineData: mockTimelineData,
    });

    render(<TaskExecutionTimelineDrawer />);

    const waterfallBtn = screen.getByText(/waterfallView/i);
    fireEvent.click(waterfallBtn);

    expect(useTaskInspectorStore.getState().viewMode).toBe('waterfall');
    // In waterfall mode, both flat nodes are visible
    expect(screen.getByText('ExtractTokens')).toBeInTheDocument();
  });

  it('selects step node and shows payload details panel', () => {
    useTaskInspectorStore.setState({
      isOpen: true,
      activeTaskId: 'task_exec_999',
      timelineData: mockTimelineData,
    });

    render(<TaskExecutionTimelineDrawer />);

    const stepRow = screen.getByText('DecomposeTask');
    fireEvent.click(stepRow);

    expect(useTaskInspectorStore.getState().selectedNodeId).toBe('node_root');
    expect(screen.getByText(/build search index/)).toBeInTheDocument();
  });

  it('handles mid-flight barge-in input submission', async () => {
    const interruptSpy = vi.spyOn(useTaskInspectorStore.getState(), 'interruptTask').mockResolvedValue();

    useTaskInspectorStore.setState({
      isOpen: true,
      activeTaskId: 'task_exec_999',
      timelineData: mockTimelineData,
    });

    render(<TaskExecutionTimelineDrawer />);

    const input = screen.getByPlaceholderText(/bargeInPlaceholder/i);
    fireEvent.change(input, { target: { value: 'Use cached index' } });

    const btn = screen.getByText(/bargeInButton/i);
    fireEvent.click(btn);

    await waitFor(() => {
      expect(interruptSpy).toHaveBeenCalledWith('user_barge_in', 'Use cached index');
    });
  });
});
