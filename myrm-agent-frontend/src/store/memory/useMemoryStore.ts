import { create } from 'zustand';
import { immer } from 'zustand/middleware/immer';
import type {
  MemoryState,
  PendingMemory,
  MemoryType,
  MemorySortBy,
  MemorySortOrder,
  UpdateMemoryRequest,
} from './types';
import type { CreateMemoryRequest } from '@/services/memory';
import {
  getPendingMemories,
  approveMemory as apiApproveMemory,
  rejectMemory as apiRejectMemory,
  batchApproveMemories,
  batchRejectMemories,
  getMemories,
  createMemory as apiCreateMemory,
  updateMemory as apiUpdateMemory,
  deleteMemory as apiDeleteMemory,
  deleteAllMemories as apiDeleteAllMemories,
  getMemoryStats as apiGetMemoryStats,
  getArchivedMemories as apiGetArchivedMemories,
  restoreMemory as apiRestoreMemory,
  purgeMemory as apiPurgeMemory,
} from '@/services/memory';

const DEFAULT_PAGE_SIZE = 20;

const initialState = {
  pendingMemories: [] as PendingMemory[],
  pendingCount: 0,
  pendingLoading: false,
  pendingError: null as string | null,
  selectedPendingIds: new Set<string>(),
  currentPendingMemory: null as PendingMemory | null,
  isConfirmDialogOpen: false,
  memories: [],
  memoriesLoading: false,
  memoriesError: null as string | null,
  memoryPagination: null,
  memoryTypeFilter: null as MemoryType | null,
  memorySearchQuery: '',
  memorySortBy: 'created_at' as MemorySortBy,
  memorySortOrder: 'desc' as MemorySortOrder,
  memoryStats: null,
  statsLoading: false,
  archivedMemories: [],
  archivedLoading: false,
  archivedPagination: null,
};

const useMemoryStore = create<MemoryState>()(
  immer((set, get) => ({
    ...initialState,

    // ==================== 待确认记忆 ====================

    fetchPendingMemories: async (force = false) => {
      const { pendingLoading, pendingMemories } = get();
      if (!force && (pendingLoading || pendingMemories.length > 0)) return;
      set({ pendingLoading: true, pendingError: null });
      try {
        const response = await getPendingMemories();
        set({
          pendingMemories: response.items,
          pendingCount: response.total,
          pendingLoading: false,
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to fetch pending memories';
        set({ pendingError: message, pendingLoading: false });
      }
    },

    approveMemory: async (id: string, editedContent?: string) => {
      try {
        await apiApproveMemory(id, editedContent);
        set((state) => {
          state.pendingMemories = state.pendingMemories.filter((m) => m.id !== id);
          state.pendingCount = Math.max(0, state.pendingCount - 1);
          state.selectedPendingIds.delete(id);
          if (state.currentPendingMemory?.id === id) {
            state.currentPendingMemory = null;
            state.isConfirmDialogOpen = false;
          }
        });
        get().fetchPendingMemories(true);
      } catch (error) {
        throw new Error(error instanceof Error ? error.message : 'Failed to approve memory');
      }
    },

    rejectMemory: async (id: string) => {
      try {
        await apiRejectMemory(id);
        set((state) => {
          state.pendingMemories = state.pendingMemories.filter((m) => m.id !== id);
          state.pendingCount = Math.max(0, state.pendingCount - 1);
          state.selectedPendingIds.delete(id);
          if (state.currentPendingMemory?.id === id) {
            state.currentPendingMemory = null;
            state.isConfirmDialogOpen = false;
          }
        });
        get().fetchPendingMemories(true);
      } catch (error) {
        throw new Error(error instanceof Error ? error.message : 'Failed to reject memory');
      }
    },

    batchApprove: async () => {
      const { selectedPendingIds } = get();
      if (selectedPendingIds.size === 0) return;
      const ids = Array.from(selectedPendingIds);
      try {
        await batchApproveMemories(ids);
        set((state) => {
          state.pendingMemories = state.pendingMemories.filter((m) => !selectedPendingIds.has(m.id));
          state.pendingCount = Math.max(0, state.pendingCount - ids.length);
          state.selectedPendingIds.clear();
        });
        get().fetchPendingMemories(true);
      } catch (error) {
        throw new Error(error instanceof Error ? error.message : 'Batch approve failed');
      }
    },

    batchReject: async () => {
      const { selectedPendingIds } = get();
      if (selectedPendingIds.size === 0) return;
      const ids = Array.from(selectedPendingIds);
      try {
        await batchRejectMemories(ids);
        set((state) => {
          state.pendingMemories = state.pendingMemories.filter((m) => !selectedPendingIds.has(m.id));
          state.pendingCount = Math.max(0, state.pendingCount - ids.length);
          state.selectedPendingIds.clear();
        });
        get().fetchPendingMemories(true);
      } catch (error) {
        throw new Error(error instanceof Error ? error.message : 'Batch reject failed');
      }
    },

    // ==================== 选择操作 ====================

    toggleSelectPending: (id: string) => {
      set((state) => {
        if (state.selectedPendingIds.has(id)) {
          state.selectedPendingIds.delete(id);
        } else {
          state.selectedPendingIds.add(id);
        }
      });
    },

    selectAllPending: () => {
      set((state) => {
        const allIds = state.pendingMemories.map((m) => m.id);
        const allSelected = allIds.every((id) => state.selectedPendingIds.has(id));
        if (allSelected) {
          state.selectedPendingIds.clear();
        } else {
          state.selectedPendingIds = new Set(allIds);
        }
      });
    },

    clearSelection: () => {
      set((state) => {
        state.selectedPendingIds.clear();
      });
    },

    // ==================== 弹窗操作 ====================

    openConfirmDialog: (memory: PendingMemory) => {
      set({ currentPendingMemory: memory, isConfirmDialogOpen: true });
    },

    closeConfirmDialog: () => {
      set({ currentPendingMemory: null, isConfirmDialogOpen: false });
    },

    // ==================== 记忆 CRUD ====================

    fetchMemories: async (page = 1) => {
      const { memoryTypeFilter, memorySearchQuery, memorySortBy, memorySortOrder } = get();
      set({ memoriesLoading: true, memoriesError: null });
      try {
        const response = await getMemories({
          type: memoryTypeFilter ?? undefined,
          search: memorySearchQuery || undefined,
          sortBy: memorySortBy,
          sortOrder: memorySortOrder,
          page,
          pageSize: DEFAULT_PAGE_SIZE,
        });
        set({
          memories: response.items,
          memoryPagination: response.pagination,
          memoriesLoading: false,
        });
      } catch (error) {
        const message = error instanceof Error ? error.message : 'Failed to fetch memories';
        set({ memoriesError: message, memoriesLoading: false });
      }
    },

    loadMoreMemories: async () => {
      const {
        memoryPagination,
        memories,
        memoriesLoading,
        memoryTypeFilter,
        memorySearchQuery,
        memorySortBy,
        memorySortOrder,
      } = get();
      if (memoriesLoading || !memoryPagination?.has_next) return;
      set({ memoriesLoading: true });
      try {
        const response = await getMemories({
          type: memoryTypeFilter ?? undefined,
          search: memorySearchQuery || undefined,
          sortBy: memorySortBy,
          sortOrder: memorySortOrder,
          page: memoryPagination.page + 1,
          pageSize: memoryPagination.page_size,
        });
        set({
          memories: [...memories, ...response.items],
          memoryPagination: response.pagination,
          memoriesLoading: false,
        });
      } catch {
        set({ memoriesLoading: false });
      }
    },

    setMemoryTypeFilter: (type: MemoryType | null) => {
      set({ memoryTypeFilter: type });
      get().fetchMemories();
    },

    setMemorySearchQuery: (query: string) => {
      set({ memorySearchQuery: query });
      get().fetchMemories();
    },

    setMemorySortBy: (sortBy: MemorySortBy) => {
      set({ memorySortBy: sortBy });
      get().fetchMemories();
    },

    setMemorySortOrder: (order: MemorySortOrder) => {
      set({ memorySortOrder: order });
      get().fetchMemories();
    },

    updateMemory: async (memoryType: MemoryType, memoryId: string, updates: UpdateMemoryRequest) => {
      try {
        const updated = await apiUpdateMemory(memoryType, memoryId, updates);
        set((state) => {
          const idx = state.memories.findIndex((m) => m.id === memoryId);
          if (idx !== -1) {
            state.memories[idx] = { ...state.memories[idx], ...updated };
          }
        });
      } catch (error) {
        throw new Error(error instanceof Error ? error.message : 'Failed to update memory');
      }
    },

    deleteMemory: async (id: string, memoryType: MemoryType) => {
      try {
        await apiDeleteMemory(id, memoryType);
        set((state) => {
          state.memories = state.memories.filter((m) => m.id !== id);
          if (state.memoryPagination) {
            state.memoryPagination.total = Math.max(0, state.memoryPagination.total - 1);
          }
        });
        get().fetchMemoryStats();
      } catch (error) {
        throw new Error(error instanceof Error ? error.message : 'Failed to delete memory');
      }
    },

    createMemory: async (body: CreateMemoryRequest) => {
      try {
        const created = await apiCreateMemory(body);
        set((state) => {
          state.memories.unshift(created);
          if (state.memoryPagination) {
            state.memoryPagination.total += 1;
          }
        });
        get().fetchMemoryStats();
        return created;
      } catch (error) {
        throw new Error(error instanceof Error ? error.message : 'Failed to create memory');
      }
    },

    deleteAllMemories: async () => {
      try {
        await apiDeleteAllMemories();
        set((state) => {
          state.memories = [];
          state.pendingMemories = [];
          state.pendingCount = 0;
          state.memoryPagination = null;
          state.memoryStats = null;
          state.selectedPendingIds = new Set<string>();
        });
      } catch (error) {
        throw new Error(error instanceof Error ? error.message : 'Failed to delete all memories');
      }
    },

    // ==================== 统计 ====================

    fetchMemoryStats: async () => {
      const { statsLoading } = get();
      if (statsLoading) return;
      set({ statsLoading: true });
      try {
        const stats = await apiGetMemoryStats();
        set({ memoryStats: stats, statsLoading: false });
      } catch {
        set({ statsLoading: false });
      }
    },

    // ==================== 回收站 ====================

    fetchArchivedMemories: async (page = 1) => {
      set({ archivedLoading: true });
      try {
        const response = await apiGetArchivedMemories({ page, pageSize: DEFAULT_PAGE_SIZE });
        set({
          archivedMemories: response.items,
          archivedPagination: response.pagination,
          archivedLoading: false,
        });
      } catch {
        set({ archivedLoading: false });
      }
    },

    restoreMemory: async (id: string) => {
      try {
        const restored = await apiRestoreMemory(id);
        set((state) => {
          state.archivedMemories = state.archivedMemories.filter((m) => m.id !== id);
          if (state.archivedPagination) {
            state.archivedPagination.total = Math.max(0, state.archivedPagination.total - 1);
          }
          state.memories.unshift(restored);
          if (state.memoryPagination) {
            state.memoryPagination.total += 1;
          }
        });
        get().fetchMemoryStats();
      } catch (error) {
        throw new Error(error instanceof Error ? error.message : 'Failed to restore memory');
      }
    },

    purgeMemory: async (id: string) => {
      try {
        await apiPurgeMemory(id);
        set((state) => {
          state.archivedMemories = state.archivedMemories.filter((m) => m.id !== id);
          if (state.archivedPagination) {
            state.archivedPagination.total = Math.max(0, state.archivedPagination.total - 1);
          }
        });
      } catch (error) {
        throw new Error(error instanceof Error ? error.message : 'Failed to purge memory');
      }
    },

    reset: () => {
      set({ ...initialState, selectedPendingIds: new Set() });
    },
  })),
);

export default useMemoryStore;
