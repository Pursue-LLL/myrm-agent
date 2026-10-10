import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as safeForgetService from '@/services/memory/safeForget';
import { useSafeEpisodicForget } from '../useSafeEpisodicForget';

vi.mock('@/services/memory/safeForget', () => ({
  probeMemoryParents: vi.fn(),
  executeSafeForget: vi.fn(),
}));

describe('useSafeEpisodicForget', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('initializes with default clean state', () => {
    const { result } = renderHook(() => useSafeEpisodicForget());

    expect(result.current.isProbing).toBe(false);
    expect(result.current.isForgetting).toBe(false);
    expect(result.current.probeResult).toBeNull();
    expect(result.current.lastResult).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('probes memory parents and updates probeResult on success', async () => {
    const mockProbeRes: safeForgetService.ParentProbeResponseDTO = {
      memory_id: 'mem_1',
      authorized: true,
      episodic_exists: true,
      competing_tiers: ['working'],
      has_competing_parents: true,
    };
    vi.mocked(safeForgetService.probeMemoryParents).mockResolvedValueOnce(mockProbeRes);

    const { result } = renderHook(() => useSafeEpisodicForget());

    let returnedRes: safeForgetService.ParentProbeResponseDTO | null = null;
    await act(async () => {
      returnedRes = await result.current.probe('mem_1', 'sess_1', true);
    });

    expect(returnedRes).toEqual(mockProbeRes);
    expect(result.current.probeResult).toEqual(mockProbeRes);
    expect(result.current.isProbing).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('executes safe forget with retention semantics on success', async () => {
    const mockForgetRes: safeForgetService.SafeForgetResponseDTO = {
      memory_id: 'mem_1',
      deleted: true,
      unauthorized: false,
      retained_shared_children: true,
      deleted_child_tables: [],
      message: 'Successfully deleted with shared retention.',
    };
    vi.mocked(safeForgetService.executeSafeForget).mockResolvedValueOnce(mockForgetRes);

    const { result } = renderHook(() => useSafeEpisodicForget());

    let returnedRes: safeForgetService.SafeForgetResponseDTO | null = null;
    await act(async () => {
      returnedRes = await result.current.forget({
        memory_id: 'mem_1',
        caller_session_id: 'sess_1',
      });
    });

    expect(returnedRes).toEqual(mockForgetRes);
    expect(result.current.lastResult).toEqual(mockForgetRes);
    expect(result.current.lastResult?.retained_shared_children).toBe(true);
    expect(result.current.isForgetting).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('sets error state when safe forget fails', async () => {
    vi.mocked(safeForgetService.executeSafeForget).mockRejectedValueOnce(
      new Error('Unauthorized session mismatch')
    );

    const { result } = renderHook(() => useSafeEpisodicForget());

    let returnedRes: safeForgetService.SafeForgetResponseDTO | null = null;
    await act(async () => {
      returnedRes = await result.current.forget({
        memory_id: 'mem_unauth',
        caller_session_id: 'sess_wrong',
      });
    });

    expect(returnedRes).toBeNull();
    expect(result.current.error).toBe('Unauthorized session mismatch');
    expect(result.current.isForgetting).toBe(false);
  });

  it('resets all state back to initial values', async () => {
    const mockProbeRes: safeForgetService.ParentProbeResponseDTO = {
      memory_id: 'mem_2',
      authorized: false,
      episodic_exists: false,
      competing_tiers: [],
      has_competing_parents: false,
    };
    vi.mocked(safeForgetService.probeMemoryParents).mockResolvedValueOnce(mockProbeRes);

    const { result } = renderHook(() => useSafeEpisodicForget());

    await act(async () => {
      await result.current.probe('mem_2', 'sess_2');
    });
    expect(result.current.probeResult).not.toBeNull();

    act(() => {
      result.current.reset();
    });

    expect(result.current.probeResult).toBeNull();
    expect(result.current.lastResult).toBeNull();
    expect(result.current.error).toBeNull();
  });
});
