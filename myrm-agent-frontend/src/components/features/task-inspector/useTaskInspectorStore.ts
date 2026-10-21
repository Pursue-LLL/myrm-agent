import { create } from 'zustand';
import type {
  TaskInspectorState,
  TaskTimelineData,
} from './taskInspectorTypes';

export const useTaskInspectorStore = create<TaskInspectorState>((set, get) => ({
  isOpen: false,
  activeTaskId: null,
  viewMode: 'tree',
  timelineData: null,
  isLoading: false,
  isInterrupting: false,
  selectedNodeId: null,
  expandedNodeIds: [],
  error: null,

  openInspector: (taskId: string) => {
    set({
      isOpen: true,
      activeTaskId: taskId,
      selectedNodeId: null,
      error: null,
    });
    void get().fetchTimeline(taskId);
  },

  closeInspector: () => {
    set({ isOpen: false, activeTaskId: null, selectedNodeId: null });
  },

  setViewMode: (mode: 'tree' | 'waterfall') => {
    set({ viewMode: mode });
  },

  selectNode: (nodeId: string | null) => {
    set({ selectedNodeId: nodeId });
  },

  toggleExpand: (nodeId: string) => {
    const current = get().expandedNodeIds;
    const exists = current.includes(nodeId);
    const updated = exists
      ? current.filter((id) => id !== nodeId)
      : [...current, nodeId];
    set({ expandedNodeIds: updated });
  },

  fetchTimeline: async (taskId: string) => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch(`/api/v1/tasks/${encodeURIComponent(taskId)}/timeline`);
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `Failed to fetch timeline: status ${res.status}`);
      }
      const data = (await res.json()) as TaskTimelineData;
      set({
        timelineData: data,
        isLoading: false,
        error: null,
      });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ isLoading: false, error: msg });
    }
  },

  interruptTask: async (reason = 'user_barge_in', instruction = '') => {
    const taskId = get().activeTaskId;
    if (!taskId) {
      return;
    }
    set({ isInterrupting: true, error: null });
    try {
      const res = await fetch(`/api/v1/tasks/${encodeURIComponent(taskId)}/interrupt`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reason, instruction }),
      });
      if (!res.ok) {
        const errText = await res.text();
        throw new Error(errText || `Failed to interrupt: status ${res.status}`);
      }
      set({ isInterrupting: false });
      // Refresh timeline snapshot
      await get().fetchTimeline(taskId);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      set({ isInterrupting: false, error: msg });
      throw err;
    }
  },
}));
