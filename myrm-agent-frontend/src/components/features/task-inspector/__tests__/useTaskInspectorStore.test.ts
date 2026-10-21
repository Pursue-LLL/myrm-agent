import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { useTaskInspectorStore } from '../useTaskInspectorStore';
import type { TaskTimelineData } from '../taskInspectorTypes';

describe('useTaskInspectorStore', () => {
  beforeEach(() => {
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

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('initializes with default closed state and tree view mode', () => {
    const state = useTaskInspectorStore.getState();
    expect(state.isOpen).toBe(false);
    expect(state.activeTaskId).toBeNull();
    expect(state.viewMode).toBe('tree');
    expect(state.timelineData).toBeNull();
    expect(state.selectedNodeId).toBeNull();
  });

  it('toggles view mode and expands nodes', () => {
    useTaskInspectorStore.getState().setViewMode('waterfall');
    expect(useTaskInspectorStore.getState().viewMode).toBe('waterfall');

    useTaskInspectorStore.getState().toggleExpand('node_1');
    expect(useTaskInspectorStore.getState().expandedNodeIds).toContain('node_1');

    useTaskInspectorStore.getState().toggleExpand('node_1');
    expect(useTaskInspectorStore.getState().expandedNodeIds).not.toContain('node_1');
  });

  it('selects and deselects nodes', () => {
    useTaskInspectorStore.getState().selectNode('node_99');
    expect(useTaskInspectorStore.getState().selectedNodeId).toBe('node_99');

    useTaskInspectorStore.getState().selectNode(null);
    expect(useTaskInspectorStore.getState().selectedNodeId).toBeNull();
  });

  it('opens inspector and fetches timeline data successfully', async () => {
    const mockData: TaskTimelineData = {
      task_id: 'task_001',
      tree: [
        {
          node_id: 'step_1',
          step_name: 'CompileAST',
          parent_id: null,
          step_index: 1,
          node_type: 'tool_invocation',
          status: 'completed',
          start_time_ms: 1000,
          end_time_ms: 1250,
          duration_ms: 250,
          input_payload: { file: 'foo.ts' },
          output_payload: { ok: 'true' },
          metrics: {
            input_chars: 100,
            output_chars: 200,
            prompt_tokens: 50,
            completion_tokens: 30,
            cache_hit: true,
          },
          error_message: null,
          children: [],
        },
      ],
      waterfall: [],
      summary: {
        total_steps: 1,
        completed_steps: 1,
        failed_steps: 0,
        running_steps: 0,
        interrupted_steps: 0,
        total_duration_ms: 250,
        total_tokens: 80,
      },
      interruptions: [],
    };

    const fetchSpy = vi.spyOn(window, 'fetch').mockResolvedValueOnce({
      ok: true,
      json: async () => mockData,
    } as Response);

    useTaskInspectorStore.getState().openInspector('task_001');

    expect(useTaskInspectorStore.getState().isOpen).toBe(true);
    expect(useTaskInspectorStore.getState().activeTaskId).toBe('task_001');

    await vi.waitFor(() => {
      expect(useTaskInspectorStore.getState().timelineData).toEqual(mockData);
    });

    expect(fetchSpy).toHaveBeenCalledWith('/api/v1/tasks/task_001/timeline');
  });

  it('handles timeline fetch errors gracefully', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValueOnce({
      ok: false,
      status: 404,
      text: async () => 'Task not found',
    } as Response);

    await useTaskInspectorStore.getState().fetchTimeline('non_existent');

    const state = useTaskInspectorStore.getState();
    expect(state.isLoading).toBe(false);
    expect(state.error).toBe('Task not found');
  });

  it('sends mid-flight barge-in interrupt and refreshes snapshot', async () => {
    useTaskInspectorStore.setState({ activeTaskId: 'task_running_1' });

    const fetchSpy = vi.spyOn(window, 'fetch')
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({ status: 'interrupted' }),
      } as Response)
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          task_id: 'task_running_1',
          tree: [],
          waterfall: [],
          summary: {
            total_steps: 1,
            completed_steps: 0,
            failed_steps: 0,
            running_steps: 0,
            interrupted_steps: 1,
            total_duration_ms: 50,
            total_tokens: 0,
          },
          interruptions: [{ reason: 'test', instruction: 'stop' }],
        }),
      } as Response);

    await useTaskInspectorStore.getState().interruptTask('user_correction', 'stop immediately');

    expect(fetchSpy).toHaveBeenCalledWith(
      '/api/v1/tasks/task_running_1/interrupt',
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      })
    );
  });
});
