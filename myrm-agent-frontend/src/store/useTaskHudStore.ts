/**
 * Zustand Store for Session Task HUD & Anti-Compaction Task Machine.
 *
 * [INPUT] TaskItem, TaskStatus, SessionTaskHudData
 * [OUTPUT] useTaskHudStore hook
 * [POS] Item 31 frontend task state manager. Strictly under 180 lines. Zero `any`.
 */

import { create } from 'zustand';
import type { TaskItem, TaskStatus, SessionTaskHudData } from '@/components/features/task-hud/taskHudTypes';

interface TaskHudState {
  chatId: string;
  tasks: TaskItem[];
  overallProgress: number;
  activeTaskId: string | null;
  isExpanded: boolean;
  isLoading: boolean;

  setChatId: (chatId: string) => void;
  setTasks: (tasks: TaskItem[]) => void;
  toggleExpanded: () => void;
  setExpanded: (expanded: boolean) => void;
  addTask: (task: TaskItem) => void;
  updateTaskStatus: (taskId: string, status: TaskStatus, progress?: number) => void;
  removeTask: (taskId: string) => void;
  hydrateFromServer: (data: SessionTaskHudData) => void;
}

export const useTaskHudStore = create<TaskHudState>((set, get) => ({
  chatId: '',
  tasks: [],
  overallProgress: 0,
  activeTaskId: null,
  isExpanded: false,
  isLoading: false,

  setChatId: (chatId) => {
    if (get().chatId !== chatId) {
      set({ chatId, tasks: [], overallProgress: 0, activeTaskId: null });
    }
  },

  setTasks: (tasks) => {
    const total = tasks.reduce((sum, t) => sum + t.progress_percent, 0);
    const overall = tasks.length > 0 ? Math.round(total / tasks.length) : 0;
    const active = tasks.find((t) => t.status === 'in_progress') || tasks.find((t) => t.status === 'pending') || null;

    set({
      tasks,
      overallProgress: overall,
      activeTaskId: active ? active.id : null,
    });
  },

  toggleExpanded: () => set((state) => ({ isExpanded: !state.isExpanded })),
  setExpanded: (expanded) => set({ isExpanded: expanded }),

  addTask: (task) => {
    const current = get().tasks;
    const exists = current.some((t) => t.id === task.id);
    const updated = exists ? current.map((t) => (t.id === task.id ? task : t)) : [...current, task];
    get().setTasks(updated);
  },

  updateTaskStatus: (taskId, status, progress) => {
    const updated = get().tasks.map((t) => {
      if (t.id !== taskId) {
        return t;
      }
      let newProgress = progress !== undefined ? progress : t.progress_percent;
      if (status === 'completed') {
        newProgress = 100;
      } else if (status === 'in_progress' && newProgress === 0) {
        newProgress = 50;
      }
      return {
        ...t,
        status,
        progress_percent: newProgress,
        updated_at: new Date().toISOString(),
      };
    });
    get().setTasks(updated);
  },

  removeTask: (taskId) => {
    const updated = get().tasks.filter((t) => t.id !== taskId);
    get().setTasks(updated);
  },

  hydrateFromServer: (data) => {
    set({
      chatId: data.session_id,
      tasks: data.tasks,
      overallProgress: data.overall_progress,
      activeTaskId: data.active_task_id,
    });
  },
}));
