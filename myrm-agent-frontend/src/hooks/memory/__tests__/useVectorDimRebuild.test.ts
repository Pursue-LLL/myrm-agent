import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as guardService from '@/services/memory/vectorDimGuard';
import { useVectorDimRebuild } from '../useVectorDimRebuild';

vi.mock('@/services/memory/vectorDimGuard', () => ({
  inspectCollectionDim: vi.fn(),
  startVectorRebuild: vi.fn(),
  getRebuildTaskStatus: vi.fn(),
  getActiveRebuildTask: vi.fn(),
}));

describe('useVectorDimRebuild', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('initializes with default clean state', () => {
    const { result } = renderHook(() => useVectorDimRebuild());

    expect(result.current.isInspecting).toBe(false);
    expect(result.current.isRebuilding).toBe(false);
    expect(result.current.inspectResult).toBeNull();
    expect(result.current.taskStatus).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('inspects collection dimension and updates inspectResult on success', async () => {
    const mockInspectRes: guardService.DimGuardInspectResponseDTO = {
      collection: 'col_test',
      exists: true,
      current_dim: 384,
      expected_dim: 1536,
      dim_match: false,
      needs_rebuild: true,
      data_intact: true,
      message: 'Dimension mismatch',
    };
    vi.mocked(guardService.inspectCollectionDim).mockResolvedValueOnce(mockInspectRes);

    const { result } = renderHook(() => useVectorDimRebuild());

    let returnedRes: guardService.DimGuardInspectResponseDTO | null = null;
    await act(async () => {
      returnedRes = await result.current.inspect('col_test', 1536);
    });

    expect(returnedRes).toEqual(mockInspectRes);
    expect(result.current.inspectResult).toEqual(mockInspectRes);
    expect(result.current.isInspecting).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('starts rebuild task and updates taskStatus on success', async () => {
    const mockStatus: guardService.RebuildTaskStatusResponseDTO = {
      task_id: 'rebuild_123',
      collection: 'col_test',
      phase: 'completed',
      progress_pct: 100,
      processed_count: 5,
      total_count: 5,
      failed_items: [],
      started_at_ms: 1000,
      finished_at_ms: 2000,
      error: null,
    };
    vi.mocked(guardService.startVectorRebuild).mockResolvedValueOnce(mockStatus);

    const { result } = renderHook(() => useVectorDimRebuild());

    let returnedStatus: guardService.RebuildTaskStatusResponseDTO | null = null;
    await act(async () => {
      returnedStatus = await result.current.rebuild({
        collection: 'col_test',
        expected_dim: 1536,
      });
    });

    expect(returnedStatus).toEqual(mockStatus);
    expect(result.current.taskStatus).toEqual(mockStatus);
    expect(result.current.isRebuilding).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('sets error state when rebuild start fails with lock conflict', async () => {
    vi.mocked(guardService.startVectorRebuild).mockRejectedValueOnce(
      new Error('Another rebuild task is currently running.')
    );

    const { result } = renderHook(() => useVectorDimRebuild());

    let returnedStatus: guardService.RebuildTaskStatusResponseDTO | null = null;
    await act(async () => {
      returnedStatus = await result.current.rebuild({
        collection: 'col_test',
        expected_dim: 1536,
      });
    });

    expect(returnedStatus).toBeNull();
    expect(result.current.error).toBe('Another rebuild task is currently running.');
    expect(result.current.isRebuilding).toBe(false);
  });

  it('refreshes task status snapshot', async () => {
    const mockStatus: guardService.RebuildTaskStatusResponseDTO = {
      task_id: 'rebuild_456',
      collection: 'col_test',
      phase: 'rebuilding',
      progress_pct: 50,
      processed_count: 2,
      total_count: 4,
      failed_items: [],
      started_at_ms: 1000,
      finished_at_ms: null,
      error: null,
    };
    vi.mocked(guardService.getRebuildTaskStatus).mockResolvedValueOnce(mockStatus);

    const { result } = renderHook(() => useVectorDimRebuild());

    let refreshed: guardService.RebuildTaskStatusResponseDTO | null = null;
    await act(async () => {
      refreshed = await result.current.refreshStatus('rebuild_456');
    });

    expect(refreshed).toEqual(mockStatus);
    expect(result.current.taskStatus).toEqual(mockStatus);
  });

  it('resets all state back to initial values', async () => {
    const mockInspectRes: guardService.DimGuardInspectResponseDTO = {
      collection: 'col_test',
      exists: true,
      current_dim: 1536,
      expected_dim: 1536,
      dim_match: true,
      needs_rebuild: false,
      data_intact: true,
      message: 'Matched',
    };
    vi.mocked(guardService.inspectCollectionDim).mockResolvedValueOnce(mockInspectRes);

    const { result } = renderHook(() => useVectorDimRebuild());

    await act(async () => {
      await result.current.inspect('col_test', 1536);
    });
    expect(result.current.inspectResult).not.toBeNull();

    act(() => {
      result.current.reset();
    });

    expect(result.current.inspectResult).toBeNull();
    expect(result.current.taskStatus).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
