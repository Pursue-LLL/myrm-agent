/**
 * [INPUT]
 * - vitest (POS: Unit test framework)
 * - @/components/features/chat-window/memory-inspector/useMemoryInspectorStore
 * - @/components/features/chat-window/memory-inspector/memoryInspectorTypes
 *
 * [OUTPUT]
 * - Store lifecycle and reactive state transitions test suite for Item 201 (P1).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { useMemoryInspectorStore } from '../useMemoryInspectorStore';
import type { MemoryEngineHealth } from '../memoryInspectorTypes';

describe('useMemoryInspectorStore', () => {
  beforeEach(() => {
    useMemoryInspectorStore.getState().resetStore();
    vi.restoreAllMocks();
  });

  it('initializes with default healthy state and closed diagnostic panel', () => {
    const state = useMemoryInspectorStore.getState();

    expect(state.health.status).toBe('ready');
    expect(state.health.provider).toBe('openai');
    expect(state.health.modelName).toBe('text-embedding-3-small');
    expect(state.health.vectorStore).toBe('sqlite_vec');
    expect(state.health.vectorDims).toBe(1536);
    expect(state.health.indexedChunksCount).toBe(4280);
    expect(state.isDiagnosing).toBe(false);
    expect(state.lastDiagnostic).toBeNull();
    expect(state.isDiagnosticPanelOpen).toBe(false);
    expect(state.reindex.isReindexing).toBe(false);
  });

  it('updates engine health via setEngineHealth partial updater', () => {
    const updatedStatus: Partial<MemoryEngineHealth> = {
      status: 'degraded',
      vectorDims: 768,
      indexedChunksCount: 5000,
    };

    useMemoryInspectorStore.getState().setEngineHealth(updatedStatus);

    const state = useMemoryInspectorStore.getState();
    expect(state.health.status).toBe('degraded');
    expect(state.health.vectorDims).toBe(768);
    expect(state.health.indexedChunksCount).toBe(5000);
    expect(state.health.provider).toBe('openai');
  });

  it('runs deep diagnostic, dispatches event, and opens diagnostic panel', async () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');

    const promise = useMemoryInspectorStore.getState().runDeepDiagnostic({
      embeddingDelay: 40,
      storageWriteDelay: 10,
      cosineSearchDelay: 15,
    });

    expect(useMemoryInspectorStore.getState().isDiagnosing).toBe(true);

    const diagnostic = await promise;

    expect(useMemoryInspectorStore.getState().isDiagnosing).toBe(false);
    expect(diagnostic.totalMs).toBe(65);
    expect(diagnostic.overallRating).toBe('optimal');
    expect(useMemoryInspectorStore.getState().lastDiagnostic).toEqual(diagnostic);
    expect(useMemoryInspectorStore.getState().isDiagnosticPanelOpen).toBe(true);

    expect(dispatchSpy).toHaveBeenCalled();
  });

  it('handles reindexing workflow: start, update progress, cancel', () => {
    const store = useMemoryInspectorStore.getState();

    store.startReindexing(1000);
    expect(useMemoryInspectorStore.getState().reindex.isReindexing).toBe(true);
    expect(useMemoryInspectorStore.getState().reindex.totalChunks).toBe(1000);
    expect(useMemoryInspectorStore.getState().reindex.processedChunks).toBe(0);

    store.updateReindexProgress(500);
    expect(useMemoryInspectorStore.getState().reindex.progressPercent).toBe(50);
    expect(useMemoryInspectorStore.getState().reindex.estimatedTokensUsed).toBe(125000);

    store.cancelReindexing();
    expect(useMemoryInspectorStore.getState().reindex.isReindexing).toBe(false);
    expect(useMemoryInspectorStore.getState().reindex.progressPercent).toBe(0);
  });

  it('completes reindexing and dispatches complete event', () => {
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    const store = useMemoryInspectorStore.getState();

    store.startReindexing(200);
    store.completeReindexing();

    const reindexState = useMemoryInspectorStore.getState().reindex;
    expect(reindexState.isReindexing).toBe(false);
    expect(reindexState.progressPercent).toBe(100);
    expect(reindexState.processedChunks).toBe(200);
    expect(reindexState.estimatedTokensUsed).toBe(50000);

    expect(dispatchSpy).toHaveBeenCalled();
  });

  it('toggles diagnostic panel explicitly and via negation toggle', () => {
    const store = useMemoryInspectorStore.getState();

    store.toggleDiagnosticPanel(true);
    expect(useMemoryInspectorStore.getState().isDiagnosticPanelOpen).toBe(true);

    store.toggleDiagnosticPanel();
    expect(useMemoryInspectorStore.getState().isDiagnosticPanelOpen).toBe(false);

    store.toggleDiagnosticPanel(false);
    expect(useMemoryInspectorStore.getState().isDiagnosticPanelOpen).toBe(false);
  });

  it('resets store to initial baseline', () => {
    const store = useMemoryInspectorStore.getState();
    store.setEngineHealth({ status: 'error' });
    store.startReindexing(500);
    store.toggleDiagnosticPanel(true);

    store.resetStore();

    const resetState = useMemoryInspectorStore.getState();
    expect(resetState.health.status).toBe('ready');
    expect(resetState.reindex.isReindexing).toBe(false);
    expect(resetState.isDiagnosticPanelOpen).toBe(false);
  });
});
