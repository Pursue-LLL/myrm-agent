import { describe, it, expect, vi, beforeEach } from 'vitest';
import { act } from '@testing-library/react';
import { enableMapSet } from 'immer';

enableMapSet();

const makePending = (id: string, content = `memory-${id}`) => ({
  id,
  user_id: 'u1',
  memory_type: 'episodic' as const,
  content,
  status: 'pending' as const,
  created_at: new Date().toISOString(),
});

const m1 = makePending('m1');
const m2 = makePending('m2');
const m3 = makePending('m3');

const mockGetPendingMemories = vi.fn();
const mockApproveMemory = vi.fn().mockResolvedValue(undefined);
const mockRejectMemory = vi.fn().mockResolvedValue(undefined);
const mockBatchApproveMemories = vi.fn().mockResolvedValue(undefined);
const mockBatchRejectMemories = vi.fn().mockResolvedValue(undefined);

vi.mock('@/services/memory', () => ({
  getPendingMemories: (...args: unknown[]) => mockGetPendingMemories(...args),
  approveMemory: (...args: unknown[]) => mockApproveMemory(...args),
  rejectMemory: (...args: unknown[]) => mockRejectMemory(...args),
  batchApproveMemories: (...args: unknown[]) => mockBatchApproveMemories(...args),
  batchRejectMemories: (...args: unknown[]) => mockBatchRejectMemories(...args),
  getMemories: vi.fn().mockResolvedValue({ items: [], pagination: null }),
  createMemory: vi.fn(),
  updateMemory: vi.fn(),
  deleteMemory: vi.fn(),
  deleteAllMemories: vi.fn(),
  getMemoryStats: vi.fn().mockResolvedValue({}),
  getArchivedMemories: vi.fn().mockResolvedValue({ items: [], pagination: null }),
  restoreMemory: vi.fn(),
  purgeMemory: vi.fn(),
}));

vi.mock('@/lib/deploy-mode', () => ({
  isLocalMode: () => true,
}));

describe('useMemoryStore - pending memory operations', () => {
  let useMemoryStore: typeof import('@/store/memory/useMemoryStore').default;

  beforeEach(async () => {
    vi.resetModules();
    mockGetPendingMemories.mockReset();
    mockApproveMemory.mockReset().mockResolvedValue(undefined);
    mockRejectMemory.mockReset().mockResolvedValue(undefined);
    mockBatchApproveMemories.mockReset().mockResolvedValue(undefined);
    mockBatchRejectMemories.mockReset().mockResolvedValue(undefined);
    const mod = await import('@/store/memory/useMemoryStore');
    useMemoryStore = mod.default;
    act(() => useMemoryStore.getState().reset());
  });

  // ==================== 连续审批核心逻辑 ====================

  describe('continuous approval', () => {
    it('should auto-advance to next pending memory after approve', async () => {
      mockGetPendingMemories.mockResolvedValue({ items: [m2, m3], total: 2 });

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2, m3],
          pendingCount: 3,
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
        });
      });

      await act(async () => {
        await useMemoryStore.getState().approveMemory('m1');
      });

      await act(async () => {
        await vi.waitFor(() => expect(mockGetPendingMemories).toHaveBeenCalled());
      });

      const state = useMemoryStore.getState();
      expect(state.pendingMemories).toHaveLength(2);
      expect(state.pendingCount).toBe(2);
      expect(state.currentPendingMemory?.id).toBe('m2');
      expect(state.isConfirmDialogOpen).toBe(true);
    });

    it('should close dialog when last pending memory is approved', async () => {
      mockGetPendingMemories.mockResolvedValue({ items: [], total: 0 });

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1],
          pendingCount: 1,
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
        });
      });

      await act(async () => {
        await useMemoryStore.getState().approveMemory('m1');
      });

      await act(async () => {
        await vi.waitFor(() => expect(mockGetPendingMemories).toHaveBeenCalled());
      });

      const state = useMemoryStore.getState();
      expect(state.pendingMemories).toHaveLength(0);
      expect(state.pendingCount).toBe(0);
      expect(state.currentPendingMemory).toBeNull();
      expect(state.isConfirmDialogOpen).toBe(false);
    });

    it('should auto-advance to next pending memory after reject', async () => {
      mockGetPendingMemories.mockResolvedValue({ items: [m2], total: 1 });

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2],
          pendingCount: 2,
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
        });
      });

      await act(async () => {
        await useMemoryStore.getState().rejectMemory('m1');
      });

      await act(async () => {
        await vi.waitFor(() => expect(mockGetPendingMemories).toHaveBeenCalled());
      });

      const state = useMemoryStore.getState();
      expect(state.pendingMemories).toHaveLength(1);
      expect(state.currentPendingMemory?.id).toBe('m2');
      expect(state.isConfirmDialogOpen).toBe(true);
    });

    it('should close dialog when last pending memory is rejected', async () => {
      mockGetPendingMemories.mockResolvedValue({ items: [], total: 0 });

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1],
          pendingCount: 1,
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
        });
      });

      await act(async () => {
        await useMemoryStore.getState().rejectMemory('m1');
      });

      await act(async () => {
        await vi.waitFor(() => expect(mockGetPendingMemories).toHaveBeenCalled());
      });

      const state = useMemoryStore.getState();
      expect(state.currentPendingMemory).toBeNull();
      expect(state.isConfirmDialogOpen).toBe(false);
    });

    it('should not affect dialog when approving a non-current memory', async () => {
      mockGetPendingMemories.mockResolvedValue({ items: [m1], total: 1 });

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2],
          pendingCount: 2,
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
        });
      });

      await act(async () => {
        await useMemoryStore.getState().approveMemory('m2');
      });

      await act(async () => {
        await vi.waitFor(() => expect(mockGetPendingMemories).toHaveBeenCalled());
      });

      const state = useMemoryStore.getState();
      expect(state.currentPendingMemory?.id).toBe('m1');
      expect(state.isConfirmDialogOpen).toBe(true);
      expect(state.pendingMemories).toHaveLength(1);
    });

    it('should pass editedContent to API when approving with edits', async () => {
      mockGetPendingMemories.mockResolvedValue({ items: [], total: 0 });

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1],
          pendingCount: 1,
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
        });
      });

      await act(async () => {
        await useMemoryStore.getState().approveMemory('m1', 'edited content');
      });

      expect(mockApproveMemory).toHaveBeenCalledWith('m1', 'edited content');
    });

    it('should handle approve chain: m1→m2→m3→close', async () => {
      mockGetPendingMemories
        .mockResolvedValueOnce({ items: [m2, m3], total: 2 })
        .mockResolvedValueOnce({ items: [m3], total: 1 })
        .mockResolvedValueOnce({ items: [], total: 0 });

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2, m3],
          pendingCount: 3,
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
        });
      });

      // Approve m1 → should show m2
      await act(async () => {
        await useMemoryStore.getState().approveMemory('m1');
      });
      await act(async () => {
        await vi.waitFor(() => expect(mockGetPendingMemories).toHaveBeenCalledTimes(1));
      });

      let state = useMemoryStore.getState();
      expect(state.currentPendingMemory?.id).toBe('m2');
      expect(state.isConfirmDialogOpen).toBe(true);

      // Approve m2 → should show m3
      await act(async () => {
        await useMemoryStore.getState().approveMemory('m2');
      });
      await act(async () => {
        await vi.waitFor(() => expect(mockGetPendingMemories).toHaveBeenCalledTimes(2));
      });

      state = useMemoryStore.getState();
      expect(state.currentPendingMemory?.id).toBe('m3');
      expect(state.isConfirmDialogOpen).toBe(true);

      // Approve m3 → dialog should close
      await act(async () => {
        await useMemoryStore.getState().approveMemory('m3');
      });
      await act(async () => {
        await vi.waitFor(() => expect(mockGetPendingMemories).toHaveBeenCalledTimes(3));
      });

      state = useMemoryStore.getState();
      expect(state.currentPendingMemory).toBeNull();
      expect(state.isConfirmDialogOpen).toBe(false);
      expect(state.pendingMemories).toHaveLength(0);
    });
  });

  // ==================== 选择操作 ====================

  describe('selection operations', () => {
    it('should remove approved id from selectedPendingIds', async () => {
      mockGetPendingMemories.mockResolvedValue({ items: [m2], total: 1 });

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2],
          pendingCount: 2,
          selectedPendingIds: new Set(['m1', 'm2']),
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
        });
      });

      await act(async () => {
        await useMemoryStore.getState().approveMemory('m1');
      });

      const state = useMemoryStore.getState();
      expect(state.selectedPendingIds.has('m1')).toBe(false);
      expect(state.selectedPendingIds.has('m2')).toBe(true);
    });

    it('toggleSelectPending should toggle selection', () => {
      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2],
          pendingCount: 2,
        });
      });

      act(() => useMemoryStore.getState().toggleSelectPending('m1'));
      expect(useMemoryStore.getState().selectedPendingIds.has('m1')).toBe(true);

      act(() => useMemoryStore.getState().toggleSelectPending('m1'));
      expect(useMemoryStore.getState().selectedPendingIds.has('m1')).toBe(false);
    });

    it('selectAllPending should toggle between select all and deselect all', () => {
      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2, m3],
          pendingCount: 3,
        });
      });

      // Select all
      act(() => useMemoryStore.getState().selectAllPending());
      let state = useMemoryStore.getState();
      expect(state.selectedPendingIds.size).toBe(3);
      expect(state.selectedPendingIds.has('m1')).toBe(true);
      expect(state.selectedPendingIds.has('m2')).toBe(true);
      expect(state.selectedPendingIds.has('m3')).toBe(true);

      // Deselect all (toggle)
      act(() => useMemoryStore.getState().selectAllPending());
      state = useMemoryStore.getState();
      expect(state.selectedPendingIds.size).toBe(0);
    });

    it('clearSelection should clear all selected ids', () => {
      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2],
          selectedPendingIds: new Set(['m1', 'm2']),
        });
      });

      act(() => useMemoryStore.getState().clearSelection());
      expect(useMemoryStore.getState().selectedPendingIds.size).toBe(0);
    });
  });

  // ==================== 弹窗操作 ====================

  describe('dialog operations', () => {
    it('openConfirmDialog should set currentPendingMemory and open dialog', () => {
      act(() => useMemoryStore.getState().openConfirmDialog(m1));

      const state = useMemoryStore.getState();
      expect(state.currentPendingMemory?.id).toBe('m1');
      expect(state.isConfirmDialogOpen).toBe(true);
    });

    it('closeConfirmDialog should clear currentPendingMemory and close dialog', () => {
      act(() => {
        useMemoryStore.setState({
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
        });
      });

      act(() => useMemoryStore.getState().closeConfirmDialog());

      const state = useMemoryStore.getState();
      expect(state.currentPendingMemory).toBeNull();
      expect(state.isConfirmDialogOpen).toBe(false);
    });
  });

  // ==================== 批量操作 ====================

  describe('batch operations', () => {
    it('batchApprove should approve all selected and clear selection', async () => {
      mockGetPendingMemories.mockResolvedValue({ items: [m3], total: 1 });

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2, m3],
          pendingCount: 3,
          selectedPendingIds: new Set(['m1', 'm2']),
        });
      });

      await act(async () => {
        await useMemoryStore.getState().batchApprove();
      });

      await act(async () => {
        await vi.waitFor(() => expect(mockBatchApproveMemories).toHaveBeenCalledTimes(1));
      });

      const state = useMemoryStore.getState();
      expect(state.selectedPendingIds.size).toBe(0);
      expect(mockBatchApproveMemories).toHaveBeenCalledWith(['m1', 'm2']);
    });

    it('batchReject should reject all selected and clear selection', async () => {
      mockGetPendingMemories.mockResolvedValue({ items: [m3], total: 1 });

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2, m3],
          pendingCount: 3,
          selectedPendingIds: new Set(['m1', 'm2']),
        });
      });

      await act(async () => {
        await useMemoryStore.getState().batchReject();
      });

      await act(async () => {
        await vi.waitFor(() => expect(mockBatchRejectMemories).toHaveBeenCalledTimes(1));
      });

      const state = useMemoryStore.getState();
      expect(state.selectedPendingIds.size).toBe(0);
      expect(mockBatchRejectMemories).toHaveBeenCalledWith(['m1', 'm2']);
    });

    it('batchApprove should no-op when nothing selected', async () => {
      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2],
          pendingCount: 2,
          selectedPendingIds: new Set(),
        });
      });

      await act(async () => {
        await useMemoryStore.getState().batchApprove();
      });

      expect(mockBatchApproveMemories).not.toHaveBeenCalled();
    });

    it('batchReject should no-op when nothing selected', async () => {
      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2],
          pendingCount: 2,
          selectedPendingIds: new Set(),
        });
      });

      await act(async () => {
        await useMemoryStore.getState().batchReject();
      });

      expect(mockBatchRejectMemories).not.toHaveBeenCalled();
    });
  });

  // ==================== 错误处理 ====================

  describe('error handling', () => {
    it('approveMemory should throw on API error', async () => {
      mockApproveMemory.mockRejectedValueOnce(new Error('Network error'));

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1],
          pendingCount: 1,
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
        });
      });

      await expect(
        act(async () => {
          await useMemoryStore.getState().approveMemory('m1');
        }),
      ).rejects.toThrow('Network error');

      // State should remain unchanged on error
      const state = useMemoryStore.getState();
      expect(state.pendingMemories).toHaveLength(1);
      expect(state.currentPendingMemory?.id).toBe('m1');
      expect(state.isConfirmDialogOpen).toBe(true);
    });

    it('rejectMemory should throw on API error', async () => {
      mockRejectMemory.mockRejectedValueOnce(new Error('Server error'));

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1],
          pendingCount: 1,
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
        });
      });

      await expect(
        act(async () => {
          await useMemoryStore.getState().rejectMemory('m1');
        }),
      ).rejects.toThrow('Server error');

      const state = useMemoryStore.getState();
      expect(state.pendingMemories).toHaveLength(1);
      expect(state.currentPendingMemory?.id).toBe('m1');
    });

    it('fetchPendingMemories should set error on failure', async () => {
      mockGetPendingMemories.mockRejectedValueOnce(new Error('Fetch failed'));

      await act(async () => {
        await useMemoryStore.getState().fetchPendingMemories(true);
      });

      const state = useMemoryStore.getState();
      expect(state.pendingError).toBe('Fetch failed');
      expect(state.pendingLoading).toBe(false);
    });
  });

  // ==================== 边界条件 ====================

  describe('edge cases', () => {
    it('pendingCount should never go below 0', async () => {
      mockGetPendingMemories.mockResolvedValue({ items: [], total: 0 });

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1],
          pendingCount: 0, // Already 0
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
        });
      });

      await act(async () => {
        await useMemoryStore.getState().approveMemory('m1');
      });

      expect(useMemoryStore.getState().pendingCount).toBe(0);
    });

    it('fetchPendingMemories should skip if already loading (non-force)', async () => {
      act(() => {
        useMemoryStore.setState({ pendingLoading: true });
      });

      await act(async () => {
        await useMemoryStore.getState().fetchPendingMemories();
      });

      expect(mockGetPendingMemories).not.toHaveBeenCalled();
    });

    it('fetchPendingMemories should skip if data exists (non-force)', async () => {
      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1],
          pendingLoading: false,
        });
      });

      await act(async () => {
        await useMemoryStore.getState().fetchPendingMemories();
      });

      expect(mockGetPendingMemories).not.toHaveBeenCalled();
    });

    it('fetchPendingMemories with force=true should fetch even if data exists', async () => {
      mockGetPendingMemories.mockResolvedValue({ items: [m1, m2], total: 2 });

      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1],
          pendingLoading: false,
        });
      });

      await act(async () => {
        await useMemoryStore.getState().fetchPendingMemories(true);
      });

      expect(mockGetPendingMemories).toHaveBeenCalled();
      expect(useMemoryStore.getState().pendingMemories).toHaveLength(2);
    });

    it('reset should clear all pending state', () => {
      act(() => {
        useMemoryStore.setState({
          pendingMemories: [m1, m2],
          pendingCount: 2,
          currentPendingMemory: m1,
          isConfirmDialogOpen: true,
          selectedPendingIds: new Set(['m1']),
          pendingError: 'some error',
        });
      });

      act(() => useMemoryStore.getState().reset());

      const state = useMemoryStore.getState();
      expect(state.pendingMemories).toHaveLength(0);
      expect(state.pendingCount).toBe(0);
      expect(state.currentPendingMemory).toBeNull();
      expect(state.isConfirmDialogOpen).toBe(false);
      expect(state.selectedPendingIds.size).toBe(0);
      expect(state.pendingError).toBeNull();
    });
  });
});
