import { act, renderHook } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as freshnessService from '@/services/memory/snapshotFreshness';
import { useSnapshotFreshness } from '../useSnapshotFreshness';

vi.mock('@/services/memory/snapshotFreshness', () => ({
  initSessionSnapshot: vi.fn(),
  recordSessionWrite: vi.fn(),
  getSnapshotFreshnessState: vi.fn(),
  getDiskReadHint: vi.fn(),
  getDeltaPatch: vi.fn(),
  resetSessionFreshness: vi.fn(),
}));

describe('useSnapshotFreshness', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  const mockDigest: freshnessService.MemorySnapshotDigestDTO = {
    digest: 'snap_123456789abc',
    session_id: 'sess_fresh_01',
    created_at: '2026-10-10T10:00:00Z',
    initial_items_count: 5,
  };

  const mockStateDirty: freshnessService.SnapshotFreshnessStateDTO = {
    session_id: 'sess_fresh_01',
    snapshot_digest: 'snap_123456789abc',
    is_dirty: true,
    deltas: [
      {
        key: 'preferred_mode',
        content: 'fast_reasoning',
        turn_index: 2,
        written_at: '2026-10-10T10:05:00Z',
        action: 'update',
      },
    ],
    latest_disk_version: 2,
  };

  const mockHint: freshnessService.DirectDiskReadHintDTO = {
    session_id: 'sess_fresh_01',
    hint_message: '【记忆快照感知契约】检测到 1 项最新事实落盘写入，请直接查盘验证。',
    affected_keys: ['preferred_mode'],
    is_dirty: true,
  };

  const mockDeltaPatch: freshnessService.DeltaPatchBlockDTO = {
    header: '### [SESSION MEMORY DELTA PATCH]',
    patches: ['- [PATCH:preferred_mode (update)] fast_reasoning'],
    formatted_block: '### [SESSION MEMORY DELTA PATCH]\n- [PATCH:preferred_mode (update)] fast_reasoning\n',
  };

  it('initializes with default clean state', () => {
    const { result } = renderHook(() => useSnapshotFreshness());

    expect(result.current.isLoading).toBe(false);
    expect(result.current.digest).toBeNull();
    expect(result.current.state).toBeNull();
    expect(result.current.diskHint).toBeNull();
    expect(result.current.deltaPatch).toBeNull();
    expect(result.current.error).toBeNull();
  });

  it('initializes snapshot digest successfully', async () => {
    vi.mocked(freshnessService.initSessionSnapshot).mockResolvedValueOnce(mockDigest);

    const { result } = renderHook(() => useSnapshotFreshness());

    let res: freshnessService.MemorySnapshotDigestDTO | null = null;
    await act(async () => {
      res = await result.current.initSnapshot({
        session_id: 'sess_fresh_01',
        initial_content: 'base prompt memory',
        items_count: 5,
      });
    });

    expect(res).toEqual(mockDigest);
    expect(result.current.digest).toEqual(mockDigest);
    expect(result.current.error).toBeNull();
  });

  it('records memory write event and updates dirty state', async () => {
    vi.mocked(freshnessService.recordSessionWrite).mockResolvedValueOnce(mockStateDirty);

    const { result } = renderHook(() => useSnapshotFreshness());

    let res: freshnessService.SnapshotFreshnessStateDTO | null = null;
    await act(async () => {
      res = await result.current.recordWrite({
        session_id: 'sess_fresh_01',
        key: 'preferred_mode',
        content: 'fast_reasoning',
        turn_index: 2,
      });
    });

    expect(res).toEqual(mockStateDirty);
    expect(result.current.state).toEqual(mockStateDirty);
    expect(result.current.state?.is_dirty).toBe(true);
    expect(result.current.state?.deltas).toHaveLength(1);
  });

  it('fetches state, disk hint, and delta patch correctly', async () => {
    vi.mocked(freshnessService.getSnapshotFreshnessState).mockResolvedValueOnce(mockStateDirty);
    vi.mocked(freshnessService.getDiskReadHint).mockResolvedValueOnce(mockHint);
    vi.mocked(freshnessService.getDeltaPatch).mockResolvedValueOnce(mockDeltaPatch);

    const { result } = renderHook(() => useSnapshotFreshness());

    await act(async () => {
      await result.current.fetchState('sess_fresh_01');
      await result.current.fetchDiskHint('sess_fresh_01');
      await result.current.fetchDeltaPatch('sess_fresh_01');
    });

    expect(result.current.state).toEqual(mockStateDirty);
    expect(result.current.diskHint).toEqual(mockHint);
    expect(result.current.deltaPatch).toEqual(mockDeltaPatch);
  });

  it('resets session freshness and clears local state', async () => {
    vi.mocked(freshnessService.resetSessionFreshness).mockResolvedValueOnce({
      status: 'ok',
      session_id: 'sess_fresh_01',
    });

    const { result } = renderHook(() => useSnapshotFreshness());

    let resetSuccess = false;
    await act(async () => {
      resetSuccess = await result.current.resetSession('sess_fresh_01');
    });

    expect(resetSuccess).toBe(true);
    expect(result.current.state).toBeNull();
    expect(result.current.diskHint).toBeNull();
    expect(result.current.deltaPatch).toBeNull();

    // Clear local state directly
    act(() => {
      result.current.clearLocalState();
    });
    expect(result.current.digest).toBeNull();
  });
});
