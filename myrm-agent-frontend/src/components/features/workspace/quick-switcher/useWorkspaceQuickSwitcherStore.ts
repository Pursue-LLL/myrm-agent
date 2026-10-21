import { create } from 'zustand';
import { useEffect } from 'react';
import type {
  WorkspaceFilterTab,
  WorkspaceItem,
  WorkspaceQuickSwitcherState,
  WorkspaceSwitchEvent,
} from './workspaceQuickSwitcherTypes';

const STORAGE_KEY = 'myrm_workspaces_registry_v1';
const CURRENT_WS_KEY = 'myrm_current_workspace_id_v1';

const INITIAL_DEFAULT_WORKSPACES: WorkspaceItem[] = [
  {
    id: 'ws-myrm-core',
    name: 'open-perplexity',
    path: '/Users/yululiu/projects/AI/open-perplexity',
    gitBranch: 'main',
    isDirty: true,
    dirtyCount: 3,
    lastOpenedAt: Date.now() - 1000 * 60 * 5,
    isFavorite: true,
    activeSessionsCount: 4,
    rulesLoaded: ['AGENTS.md', '.rules', 'PROMPTS.md'],
  },
  {
    id: 'ws-frontend-app',
    name: 'myrm-agent-frontend',
    path: '/Users/yululiu/projects/AI/open-perplexity/myrm-agent/myrm-agent-frontend',
    gitBranch: 'feat/quick-switcher',
    isDirty: false,
    dirtyCount: 0,
    lastOpenedAt: Date.now() - 1000 * 60 * 30,
    isFavorite: true,
    activeSessionsCount: 2,
    rulesLoaded: ['ESLINT.md', 'TAILWIND.md'],
  },
  {
    id: 'ws-server-engine',
    name: 'myrm-agent-server',
    path: '/Users/yululiu/projects/AI/open-perplexity/myrm-agent/myrm-agent-server',
    gitBranch: 'main',
    isDirty: false,
    dirtyCount: 0,
    lastOpenedAt: Date.now() - 1000 * 60 * 180,
    isFavorite: false,
    activeSessionsCount: 1,
    rulesLoaded: ['FASTAPI.md', 'ALEMBIC.md'],
  },
];

function loadStoredWorkspaces(): WorkspaceItem[] {
  if (typeof window === 'undefined') {
    return INITIAL_DEFAULT_WORKSPACES;
  }
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return INITIAL_DEFAULT_WORKSPACES;
    }
    const parsed = JSON.parse(raw) as WorkspaceItem[];
    if (Array.isArray(parsed) && parsed.length > 0) {
      return parsed;
    }
  } catch {
    // 忽略解析错误，回退默认
  }
  return INITIAL_DEFAULT_WORKSPACES;
}

function loadStoredCurrentId(workspaces: WorkspaceItem[]): string {
  if (typeof window === 'undefined') {
    return workspaces[0]?.id ?? '';
  }
  try {
    const raw = window.localStorage.getItem(CURRENT_WS_KEY);
    if (raw && workspaces.some((w) => w.id === raw)) {
      return raw;
    }
  } catch {
    // 忽略异常
  }
  return workspaces[0]?.id ?? '';
}

export function filterWorkspaces(
  items: WorkspaceItem[],
  query: string,
  tab: WorkspaceFilterTab
): WorkspaceItem[] {
  let list = [...items];

  if (tab === 'favorites') {
    list = list.filter((item) => item.isFavorite);
  } else if (tab === 'recent') {
    list.sort((a, b) => b.lastOpenedAt - a.lastOpenedAt);
  }

  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) {
    return list;
  }

  return list.filter((item) => {
    return (
      item.name.toLowerCase().includes(normalizedQuery) ||
      item.path.toLowerCase().includes(normalizedQuery) ||
      (item.gitBranch && item.gitBranch.toLowerCase().includes(normalizedQuery)) ||
      item.rulesLoaded.some((r) => r.toLowerCase().includes(normalizedQuery))
    );
  });
}

interface WorkspaceQuickSwitcherActions {
  openSwitcher: () => void;
  closeSwitcher: () => void;
  toggleSwitcher: () => void;
  setSearchQuery: (query: string) => void;
  setActiveTab: (tab: WorkspaceFilterTab) => void;
  setSelectedIndex: (index: number) => void;
  selectNext: () => void;
  selectPrevious: () => void;
  toggleFavorite: (id: string) => void;
  switchWorkspace: (id: string, openInNewTab?: boolean) => WorkspaceItem | null;
  addWorkspace: (
    workspace: Omit<WorkspaceItem, 'lastOpenedAt' | 'isFavorite' | 'activeSessionsCount' | 'rulesLoaded'> & {
      isFavorite?: boolean;
      rulesLoaded?: string[];
    }
  ) => WorkspaceItem;
  removeWorkspace: (id: string) => void;
  resetToDefaults: () => void;
}

export type WorkspaceQuickSwitcherStore = WorkspaceQuickSwitcherState &
  WorkspaceQuickSwitcherActions;

const initialWorkspaces = loadStoredWorkspaces();
const initialCurrentId = loadStoredCurrentId(initialWorkspaces);

export const useWorkspaceQuickSwitcherStore = create<WorkspaceQuickSwitcherStore>(
  (set, get) => ({
    isOpen: false,
    searchQuery: '',
    activeTab: 'all',
    selectedIndex: 0,
    workspaces: initialWorkspaces,
    currentWorkspaceId: initialCurrentId,
    lastSwitchEvent: null,

    openSwitcher: () => {
      set({ isOpen: true, searchQuery: '', selectedIndex: 0 });
    },

    closeSwitcher: () => {
      set({ isOpen: false, searchQuery: '', selectedIndex: 0 });
    },

    toggleSwitcher: () => {
      const state = get();
      if (state.isOpen) {
        set({ isOpen: false, searchQuery: '', selectedIndex: 0 });
      } else {
        set({ isOpen: true, searchQuery: '', selectedIndex: 0 });
      }
    },

    setSearchQuery: (searchQuery: string) => {
      set({ searchQuery, selectedIndex: 0 });
    },

    setActiveTab: (activeTab: WorkspaceFilterTab) => {
      set({ activeTab, selectedIndex: 0 });
    },

    setSelectedIndex: (selectedIndex: number) => {
      set({ selectedIndex });
    },

    selectNext: () => {
      const state = get();
      const filtered = filterWorkspaces(state.workspaces, state.searchQuery, state.activeTab);
      if (filtered.length === 0) {
        return;
      }
      const nextIndex = (state.selectedIndex + 1) % filtered.length;
      set({ selectedIndex: nextIndex });
    },

    selectPrevious: () => {
      const state = get();
      const filtered = filterWorkspaces(state.workspaces, state.searchQuery, state.activeTab);
      if (filtered.length === 0) {
        return;
      }
      const prevIndex = (state.selectedIndex - 1 + filtered.length) % filtered.length;
      set({ selectedIndex: prevIndex });
    },

    toggleFavorite: (id: string) => {
      const state = get();
      const updated = state.workspaces.map((item) => {
        if (item.id === id) {
          return { ...item, isFavorite: !item.isFavorite };
        }
        return item;
      });
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
      }
      set({ workspaces: updated });
    },

    switchWorkspace: (id: string, openInNewTab = false) => {
      const state = get();
      const target = state.workspaces.find((w) => w.id === id);
      if (!target) {
        return null;
      }

      const now = Date.now();
      const updated = state.workspaces.map((item) => {
        if (item.id === id) {
          return { ...item, lastOpenedAt: now };
        }
        return item;
      });

      const event: WorkspaceSwitchEvent = {
        previousWorkspaceId: state.currentWorkspaceId,
        currentWorkspaceId: id,
        workspace: { ...target, lastOpenedAt: now },
        openInNewTab,
      };

      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
        if (!openInNewTab) {
          window.localStorage.setItem(CURRENT_WS_KEY, id);
        }
      }

      set({
        workspaces: updated,
        currentWorkspaceId: openInNewTab ? state.currentWorkspaceId : id,
        lastSwitchEvent: event,
        isOpen: false,
      });

      return target;
    },

    addWorkspace: (input) => {
      const state = get();
      const newWorkspace: WorkspaceItem = {
        ...input,
        lastOpenedAt: Date.now(),
        isFavorite: input.isFavorite ?? false,
        activeSessionsCount: 0,
        rulesLoaded: input.rulesLoaded ?? ['AGENTS.md'],
      };
      const updated = [newWorkspace, ...state.workspaces];
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
        window.localStorage.setItem(CURRENT_WS_KEY, newWorkspace.id);
      }
      set({
        workspaces: updated,
        currentWorkspaceId: newWorkspace.id,
        isOpen: false,
      });
      return newWorkspace;
    },

    removeWorkspace: (id: string) => {
      const state = get();
      const updated = state.workspaces.filter((w) => w.id !== id);
      let nextCurrent = state.currentWorkspaceId;
      if (state.currentWorkspaceId === id) {
        nextCurrent = updated[0]?.id ?? null;
      }
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
        if (nextCurrent) {
          window.localStorage.setItem(CURRENT_WS_KEY, nextCurrent);
        }
      }
      set({ workspaces: updated, currentWorkspaceId: nextCurrent });
    },

    resetToDefaults: () => {
      if (typeof window !== 'undefined') {
        window.localStorage.removeItem(STORAGE_KEY);
        window.localStorage.removeItem(CURRENT_WS_KEY);
      }
      set({
        workspaces: INITIAL_DEFAULT_WORKSPACES,
        currentWorkspaceId: INITIAL_DEFAULT_WORKSPACES[0]?.id ?? null,
        isOpen: false,
        searchQuery: '',
        selectedIndex: 0,
      });
    },
  })
);

export function useGlobalQuickOpenShortcut() {
  const toggleSwitcher = useWorkspaceQuickSwitcherStore((s) => s.toggleSwitcher);
  const isOpen = useWorkspaceQuickSwitcherStore((s) => s.isOpen);
  const closeSwitcher = useWorkspaceQuickSwitcherStore((s) => s.closeSwitcher);

  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && (e.key === 'o' || e.key === 'O')) {
        e.preventDefault();
        toggleSwitcher();
        return;
      }
      if (isOpen && e.key === 'Escape') {
        e.preventDefault();
        closeSwitcher();
      }
    }

    window.addEventListener('keydown', handleKeyDown);
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
    };
  }, [toggleSwitcher, isOpen, closeSwitcher]);
}
