/**
 * Task state management (Zustand store).
 *
 * Manages:
 * - Active tasks map
 * - Task CRUD operations
 * - Task subscriptions
 */

import { create } from 'zustand';
import type { Task } from './types';
import { apiRequest } from '@/lib/api';

interface TaskState {
  tasks: Map<string, Task>;

  // Actions
  addTask: (task: Task) => void;
  updateTask: (task_id: string, updates: Partial<Task>) => void;
  removeTask: (task_id: string) => void;
  getTasks: (task_ids: string[]) => Task[];

  // API calls
  fetchTask: (task_id: string) => Promise<Task | null>;
  cancelTask: (task_id: string) => Promise<void>;
  retryTask: (task_id: string) => Promise<void>;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: new Map(),

  addTask: (task) => {
    set((state) => {
      const tasks = new Map(state.tasks);
      tasks.set(task.task_id, task);
      return { tasks };
    });
  },

  updateTask: (task_id, updates) => {
    set((state) => {
      const tasks = new Map(state.tasks);
      const task = tasks.get(task_id);
      if (task) {
        tasks.set(task_id, { ...task, ...updates });
      }
      return { tasks };
    });
  },

  removeTask: (task_id) => {
    set((state) => {
      const tasks = new Map(state.tasks);
      tasks.delete(task_id);
      return { tasks };
    });
  },

  getTasks: (task_ids) => {
    const { tasks } = get();
    return task_ids.map((id) => tasks.get(id)).filter(Boolean) as Task[];
  },

  fetchTask: async (task_id) => {
    try {
      const task = await apiRequest<Task>(`/tasks/${task_id}`);
      get().addTask(task);
      return task;
    } catch (error) {
      console.error('Failed to fetch task:', error);
      return null;
    }
  },

  cancelTask: async (task_id) => {
    try {
      await apiRequest(`/tasks/${task_id}/cancel`, { method: 'POST' });
      get().updateTask(task_id, { status: 'cancelled' });
    } catch (error) {
      console.error('Failed to cancel task:', error);
      throw error;
    }
  },

  retryTask: async (task_id) => {
    try {
      await apiRequest(`/tasks/${task_id}/retry`, { method: 'POST' });
      get().updateTask(task_id, { status: 'pending' });
    } catch (error) {
      console.error('Failed to retry task:', error);
      throw error;
    }
  },
}));
