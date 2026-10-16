/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { MemoryReindexStatus } from '@/services/memory/reindex';

const estimateMock = vi.fn();
const startMock = vi.fn();
const statusMock = vi.fn();

vi.mock('@/services/memory/reindex', () => ({
  getMemoryOrphanEstimate: (...args: unknown[]) => estimateMock(...args),
  startMemoryReindex: (...args: unknown[]) => startMock(...args),
  getMemoryReindexStatus: (...args: unknown[]) => statusMock(...args),
}));

import useRetrievalStore, { REINDEX_POLL_INTERVAL_MS, REINDEX_POLL_MAX_CONSECUTIVE_ERRORS } from '../useRetrievalStore';

function status(overrides: Partial<MemoryReindexStatus> = {}): MemoryReindexStatus {
  return { state: 'running', done: 0, total: 0, result: null, ...overrides };
}

const finished = (migrated: number, skipped: number, failed: number): MemoryReindexStatus =>
  status({
    state: 'succeeded',
    done: migrated + skipped + failed,
    total: migrated + skipped + failed,
    result: { migrated, skipped, failed },
  });

/** Starts the migration and advances the poll timer until it settles. */
async function runToEnd(): Promise<void> {
  const run = useRetrievalStore.getState().executeReindex();
  await vi.runAllTimersAsync();
  await run;
}

describe('memory migration after an embedding model switch', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.spyOn(console, 'warn').mockImplementation(() => {});
    estimateMock.mockReset();
    startMock.mockReset();
    statusMock.mockReset();
    useRetrievalStore.setState({
      orphanCount: 12,
      orphanOldModels: ['old-model'],
      reindexStatus: 'idle',
      reindexProgress: { done: 0, total: 0 },
      reindexResult: null,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('shows the leftover memories after a switch from the estimate', async () => {
    estimateMock.mockResolvedValueOnce({
      total_memories: 7,
      orphan_collections: [{ old_model_suffix: 'a' }, { old_model_suffix: 'a' }, { old_model_suffix: 'b' }],
    });

    await useRetrievalStore.getState().checkOrphanCollections();

    expect(useRetrievalStore.getState().orphanCount).toBe(7);
    expect(useRetrievalStore.getState().orphanOldModels).toEqual(['a', 'b']);
  });

  it('follows the background run to the end and clears the reminder when every memory moved', async () => {
    startMock.mockResolvedValueOnce(status({ done: 0, total: 12 }));
    statusMock.mockResolvedValueOnce(status({ done: 5, total: 12 })).mockResolvedValueOnce(finished(10, 2, 0));
    const progress: number[] = [];
    const unsubscribe = useRetrievalStore.subscribe((state) => progress.push(state.reindexProgress.done));

    await runToEnd();
    unsubscribe();

    const state = useRetrievalStore.getState();
    expect(state.reindexStatus).toBe('done');
    expect(state.reindexResult).toEqual({ migrated: 10, skipped: 2, failed: 0 });
    expect(state.orphanCount).toBe(0);
    expect(state.orphanOldModels).toEqual([]);
    expect(progress).toContain(5);
    expect(statusMock).toHaveBeenCalledTimes(2);
  });

  it('keeps the reminder for the memories that could not move, so another run retries them', async () => {
    startMock.mockResolvedValueOnce(finished(9, 0, 3));

    await runToEnd();

    const state = useRetrievalStore.getState();
    expect(state.reindexStatus).toBe('done');
    expect(state.reindexResult).toEqual({ migrated: 9, skipped: 0, failed: 3 });
    expect(state.orphanCount).toBe(3);
    expect(state.orphanOldModels).toEqual(['old-model']);
  });

  it('reports an interrupted run instead of claiming success when the request fails', async () => {
    startMock.mockRejectedValueOnce(new Error('network down'));

    await runToEnd();

    const state = useRetrievalStore.getState();
    expect(state.reindexStatus).toBe('error');
    expect(state.reindexResult).toBeNull();
    expect(state.orphanCount).toBe(12);
  });

  it('survives a few failed status reads but gives up when the server stays unreachable', async () => {
    startMock.mockResolvedValueOnce(status({ total: 12 }));
    statusMock.mockRejectedValueOnce(new Error('blip')).mockResolvedValueOnce(finished(12, 0, 0));
    await runToEnd();
    expect(useRetrievalStore.getState().reindexStatus).toBe('done');

    startMock.mockResolvedValueOnce(status({ total: 12 }));
    statusMock.mockReset();
    statusMock.mockRejectedValue(new Error('offline'));
    await runToEnd();

    expect(useRetrievalStore.getState().reindexStatus).toBe('error');
    expect(statusMock).toHaveBeenCalledTimes(REINDEX_POLL_MAX_CONSECUTIVE_ERRORS);
  });

  it('treats a run the server forgot (restart) as interrupted', async () => {
    startMock.mockResolvedValueOnce(status({ total: 12 }));
    statusMock.mockResolvedValueOnce(status({ state: 'idle' }));

    await runToEnd();

    expect(useRetrievalStore.getState().reindexStatus).toBe('error');
  });

  it('treats a failed server run as interrupted', async () => {
    startMock.mockResolvedValueOnce(status({ state: 'failed' }));

    await runToEnd();

    expect(useRetrievalStore.getState().reindexStatus).toBe('error');
  });

  it('ignores a second start while a run is being followed', async () => {
    startMock.mockResolvedValueOnce(status({ total: 12 }));
    statusMock.mockResolvedValueOnce(finished(12, 0, 0));

    const first = useRetrievalStore.getState().executeReindex();
    await vi.advanceTimersByTimeAsync(0);
    await useRetrievalStore.getState().executeReindex();
    await vi.advanceTimersByTimeAsync(REINDEX_POLL_INTERVAL_MS);
    await first;

    expect(startMock).toHaveBeenCalledTimes(1);
    expect(useRetrievalStore.getState().reindexStatus).toBe('done');
  });

  it('keeps the estimate of a model applied during the run instead of clearing the reminder', async () => {
    useRetrievalStore.setState({ embeddingAppliedAt: 1000 });
    startMock.mockResolvedValueOnce(status({ total: 12 }));
    statusMock.mockImplementationOnce(async () => {
      useRetrievalStore.setState({ embeddingAppliedAt: 2000, orphanCount: 30, orphanOldModels: ['older-model'] });
      return finished(12, 0, 0);
    });

    await runToEnd();

    const state = useRetrievalStore.getState();
    expect(state.reindexStatus).toBe('idle');
    expect(state.reindexResult).toBeNull();
    expect(state.orphanCount).toBe(30);
    expect(state.orphanOldModels).toEqual(['older-model']);
  });

  it('dismissing clears the reminder and any shown outcome', () => {
    useRetrievalStore.setState({ reindexStatus: 'done', reindexResult: { migrated: 1, skipped: 0, failed: 1 } });

    useRetrievalStore.getState().dismissOrphanWarning();

    const state = useRetrievalStore.getState();
    expect(state.orphanCount).toBe(0);
    expect(state.reindexStatus).toBe('idle');
    expect(state.reindexResult).toBeNull();
  });
});
