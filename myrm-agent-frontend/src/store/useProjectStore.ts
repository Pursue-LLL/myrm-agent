/**
 * [INPUT] @/services/projects
 * [OUTPUT] useProjectStore: 项目状态管理
 * [POS] 管理项目列表和当前筛选的项目，驱动侧边栏 ProjectBar 和聊天列表过滤。
 */

import { create } from 'zustand';
import { persist } from 'zustand/middleware';

import type { Project } from '@/services/projects';
import {
  getProjects,
  createProject,
  updateProject as apiUpdateProject,
  deleteProject as apiDeleteProject,
} from '@/services/projects';

interface ProjectState {
  projects: Project[];
  /** undefined = 不过滤（全部）, null = 仅未归属, string = 指定项目 */
  activeFilter: string | null | undefined;
  loaded: boolean;
}

interface ProjectActions {
  fetchProjects: () => Promise<void>;
  setActiveFilter: (filter: string | null | undefined) => void;
  addProject: (name: string, color?: string) => Promise<Project>;
  updateProject: (id: string, updates: { name?: string; color?: string }) => Promise<void>;
  removeProject: (id: string) => Promise<void>;
}

export const useProjectStore = create<ProjectState & ProjectActions>()(
  persist(
    (set, get) => ({
      projects: [],
      activeFilter: undefined,
      loaded: false,

      fetchProjects: async () => {
        const projects = await getProjects();
        set({ projects, loaded: true });
      },

      setActiveFilter: (filter) => {
        set({ activeFilter: filter });
      },

      addProject: async (name, color) => {
        const project = await createProject(name, color);
        set((s) => ({ projects: [...s.projects, project] }));
        return project;
      },

      updateProject: async (id, updates) => {
        const project = await apiUpdateProject(id, updates);
        set((s) => ({
          projects: s.projects.map((p) => (p.id === id ? project : p)),
        }));
      },

      removeProject: async (id) => {
        await apiDeleteProject(id);
        const { activeFilter } = get();
        set((s) => ({
          projects: s.projects.filter((p) => p.id !== id),
          activeFilter: activeFilter === id ? undefined : activeFilter,
        }));
      },
    }),
    {
      name: 'project-store',
      partialize: (state) => ({ activeFilter: state.activeFilter }),
    },
  ),
);
