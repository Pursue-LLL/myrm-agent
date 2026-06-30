import type {
  PendingMemory,
  Memory,
  MemoryType,
  MemoryStatusType,
  MemoryPaginationInfo,
  MemoryStatsResponse,
  TasteSummaryResponse,
  UpdateMemoryRequest,
  CreateMemoryRequest,
  MemorySortBy,
  MemorySortOrder,
  ConflictResolution,
} from '@/services/memory';

export type {
  PendingMemory,
  Memory,
  MemoryType,
  MemoryStatusType,
  MemoryPaginationInfo,
  MemoryStatsResponse,
  TasteSummaryResponse,
  UpdateMemoryRequest,
  CreateMemoryRequest,
  MemorySortBy,
  MemorySortOrder,
  ConflictResolution,
};

export interface MemoryState {
  // 待确认记忆
  pendingMemories: PendingMemory[];
  pendingCount: number;
  pendingLoading: boolean;
  pendingError: string | null;
  selectedPendingIds: Set<string>;
  currentPendingMemory: PendingMemory | null;
  isConfirmDialogOpen: boolean;

  // 已确认记忆
  memories: Memory[];
  memoriesLoading: boolean;
  memoriesError: string | null;
  memoryPagination: MemoryPaginationInfo | null;
  memoryTypeFilter: MemoryType | null;
  memoryTagFilter: string | null;
  memorySearchQuery: string;
  memorySortBy: MemorySortBy;
  memorySortOrder: MemorySortOrder;

  // 统计
  memoryStats: MemoryStatsResponse | null;
  statsLoading: boolean;

  // 冲突
  conflicts: PendingMemory[];
  conflictCount: number;
  conflictsLoading: boolean;

  // 回收站
  archivedMemories: Memory[];
  archivedLoading: boolean;
  archivedPagination: MemoryPaginationInfo | null;

  // 待确认记忆操作
  fetchPendingMemories: (force?: boolean) => Promise<void>;
  approveMemory: (id: string, editedContent?: string) => Promise<void>;
  rejectMemory: (id: string) => Promise<void>;
  batchApprove: () => Promise<void>;
  batchReject: () => Promise<void>;

  // 选择操作
  toggleSelectPending: (id: string) => void;
  selectAllPending: () => void;
  clearSelection: () => void;

  // 弹窗操作
  openConfirmDialog: (memory: PendingMemory) => void;
  closeConfirmDialog: () => void;

  // 记忆 CRUD
  createMemory: (body: CreateMemoryRequest) => Promise<Memory>;
  fetchMemories: (page?: number) => Promise<void>;
  loadMoreMemories: () => Promise<void>;
  setMemoryTypeFilter: (type: MemoryType | null) => void;
  setMemoryTagFilter: (tag: string | null) => void;
  setMemorySearchQuery: (query: string) => void;
  setMemorySortBy: (sortBy: MemorySortBy) => void;
  setMemorySortOrder: (order: MemorySortOrder) => void;
  updateMemory: (memoryType: MemoryType, memoryId: string, updates: UpdateMemoryRequest) => Promise<void>;
  deleteMemory: (id: string, memoryType: MemoryType) => Promise<void>;
  deleteAllMemories: () => Promise<void>;

  // 统计
  fetchMemoryStats: () => Promise<void>;

  // 冲突操作
  fetchConflicts: () => Promise<void>;
  resolveConflict: (id: string, resolution: ConflictResolution, mergedContent?: string) => Promise<void>;

  // 回收站操作
  fetchArchivedMemories: (page?: number) => Promise<void>;
  restoreMemory: (id: string) => Promise<void>;
  purgeMemory: (id: string) => Promise<void>;

  reset: () => void;
}
