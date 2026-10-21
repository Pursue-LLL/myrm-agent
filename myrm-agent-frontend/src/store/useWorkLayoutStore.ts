/**
 * [INPUT]
 * - Zustand create hook
 *
 * [OUTPUT]
 * - ViewMode: ('chat' | 'work')
 * - ComputeTier: ('turbo' | 'pro')
 * - WorkSidebarTab: ('tasks' | 'skills' | 'connectors' | 'partners')
 * - WorkTaskItem: Task model with checklist & progress
 * - useWorkLayoutStore: Store for dual-mode layout & compute tier selector
 *
 * [POS]
 * Dual-Mode Chat/Work Layout & Turbo/Pro Compute Selector state management (Item 26).
 * Single file < 200 lines. Zero `any` types.
 */

import { create } from 'zustand';

export type ViewMode = 'chat' | 'work';
export type ComputeTier = 'turbo' | 'pro';
export type WorkSidebarTab = 'tasks' | 'skills' | 'connectors' | 'partners';

export interface WorkSubtask {
  id: string;
  title: string;
  completed: boolean;
}

export interface WorkTaskItem {
  id: string;
  title: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  progressPercentage: number;
  subtasks: WorkSubtask[];
}

export interface WorkLayoutState {
  viewMode: ViewMode;
  computeTier: ComputeTier;
  workSidebarTab: WorkSidebarTab;
  isSidebarCollapsed: boolean;
  activeTaskId: string | null;
  tasks: WorkTaskItem[];

  // Actions
  setViewMode: (mode: ViewMode) => void;
  toggleViewMode: () => void;
  setComputeTier: (tier: ComputeTier) => void;
  toggleComputeTier: () => void;
  setWorkSidebarTab: (tab: WorkSidebarTab) => void;
  setSidebarCollapsed: (collapsed: boolean) => void;
  toggleSidebarCollapsed: () => void;
  setActiveTaskId: (id: string | null) => void;
  updateTaskStatus: (taskId: string, status: WorkTaskItem['status'], progress?: number) => void;
  toggleSubtask: (taskId: string, subtaskId: string) => void;
}

const DEFAULT_TASKS: WorkTaskItem[] = [
  {
    id: 'task-1',
    title: 'Cross-module dependency analysis',
    status: 'completed',
    progressPercentage: 100,
    subtasks: [
      { id: 'sub-1', title: 'Scan import hierarchy', completed: true },
      { id: 'sub-2', title: 'Verify cyclic dependencies', completed: true },
    ],
  },
  {
    id: 'task-2',
    title: 'Dual-mode layout component assembly',
    status: 'in_progress',
    progressPercentage: 65,
    subtasks: [
      { id: 'sub-3', title: 'Build mode switch slider', completed: true },
      { id: 'sub-4', title: 'Assemble four-dimension asset sidebar', completed: false },
      { id: 'sub-5', title: 'Connect Turbo/Pro model tier selector', completed: false },
    ],
  },
  {
    id: 'task-3',
    title: 'Unit test coverage & gate verification',
    status: 'pending',
    progressPercentage: 0,
    subtasks: [
      { id: 'sub-6', title: 'Vitest component test cases', completed: false },
      { id: 'sub-7', title: 'Oxlint 0-warning verification', completed: false },
    ],
  },
];

export const useWorkLayoutStore = create<WorkLayoutState>((set) => ({
  viewMode: 'chat',
  computeTier: 'turbo',
  workSidebarTab: 'tasks',
  isSidebarCollapsed: false,
  activeTaskId: 'task-2',
  tasks: DEFAULT_TASKS,

  setViewMode: (mode: ViewMode) => set({ viewMode: mode }),

  toggleViewMode: () =>
    set((state) => ({
      viewMode: state.viewMode === 'chat' ? 'work' : 'chat',
    })),

  setComputeTier: (tier: ComputeTier) => set({ computeTier: tier }),

  toggleComputeTier: () =>
    set((state) => ({
      computeTier: state.computeTier === 'turbo' ? 'pro' : 'turbo',
    })),

  setWorkSidebarTab: (tab: WorkSidebarTab) => set({ workSidebarTab: tab }),

  setSidebarCollapsed: (collapsed: boolean) => set({ isSidebarCollapsed: collapsed }),

  toggleSidebarCollapsed: () =>
    set((state) => ({ isSidebarCollapsed: !state.isSidebarCollapsed })),

  setActiveTaskId: (id: string | null) => set({ activeTaskId: id }),

  updateTaskStatus: (taskId: string, status: WorkTaskItem['status'], progress?: number) =>
    set((state) => ({
      tasks: state.tasks.map((t) => {
        if (t.id !== taskId) {
          return t;
        }
        return {
          ...t,
          status,
          progressPercentage: progress !== undefined ? progress : t.progressPercentage,
        };
      }),
    })),

  toggleSubtask: (taskId: string, subtaskId: string) =>
    set((state) => ({
      tasks: state.tasks.map((task) => {
        if (task.id !== taskId) {
          return task;
        }
        const updatedSubtasks = task.subtasks.map((sub) =>
          sub.id === subtaskId ? { ...sub, completed: !sub.completed } : sub,
        );
        const completedCount = updatedSubtasks.filter((s) => s.completed).length;
        const newProgress = Math.round((completedCount / updatedSubtasks.length) * 100);
        return {
          ...task,
          subtasks: updatedSubtasks,
          progressPercentage: newProgress,
          status: newProgress === 100 ? 'completed' : newProgress > 0 ? 'in_progress' : task.status,
        };
      }),
    })),
}));
