/**
 * [INPUT]
 * - @/components/features/chat-window/memory-inspector/memoryInspectorTypes
 *
 * [OUTPUT]
 * - Type definition assertions and domain contract validations for Item 201.
 */

import { describe, it, expect } from 'vitest';
import type {
  MemoryProviderStatus,
  VectorStoreType,
  LatencyRating,
  MemoryEngineHealth,
  DiagnosticLatencyBreakdown,
  ReindexProgress,
  MemoryInspectorEventPayload,
  MemoryInspectorStoreState,
} from '../memoryInspectorTypes';

describe('MemoryInspectorTypes Contracts', () => {
  it('should accept valid MemoryProviderStatus, VectorStoreType, and LatencyRating values', () => {
    const statuses: MemoryProviderStatus[] = ['ready', 'degraded', 'error', 'testing'];
    expect(statuses).toHaveLength(4);

    const storeTypes: VectorStoreType[] = [
      'sqlite_vec',
      'qdrant',
      'pgvector',
      'memory_ephemeral',
    ];
    expect(storeTypes).toHaveLength(4);

    const ratings: LatencyRating[] = ['optimal', 'acceptable', 'degraded'];
    expect(ratings).toHaveLength(3);
  });

  it('should construct a valid MemoryEngineHealth entity', () => {
    const health: MemoryEngineHealth = {
      provider: 'openai',
      status: 'ready',
      modelName: 'text-embedding-3-small',
      vectorStore: 'sqlite_vec',
      vectorDims: 1536,
      indexedChunksCount: 5000,
      ftsEntriesCount: 4200,
      lastSyncAt: 1760000000000,
    };

    expect(health.provider).toBe('openai');
    expect(health.status).toBe('ready');
    expect(health.vectorDims).toBe(1536);
    expect(health.indexedChunksCount).toBe(5000);
  });

  it('should conform to DiagnosticLatencyBreakdown and ReindexProgress contracts', () => {
    const breakdown: DiagnosticLatencyBreakdown = {
      embeddingMs: 40,
      storageWriteMs: 10,
      cosineSearchMs: 15,
      totalMs: 65,
      overallRating: 'optimal',
      probedAt: 1760000001000,
    };

    const reindex: ReindexProgress = {
      isReindexing: true,
      progressPercent: 65,
      processedChunks: 3250,
      totalChunks: 5000,
      estimatedTokensUsed: 812500,
    };

    expect(breakdown.overallRating).toBe('optimal');
    expect(breakdown.totalMs).toBe(65);
    expect(reindex.progressPercent).toBe(65);
    expect(reindex.estimatedTokensUsed).toBe(812500);
  });

  it('should construct a valid MemoryInspectorStoreState entity', () => {
    const state: MemoryInspectorStoreState = {
      health: {
        provider: 'openai',
        status: 'ready',
        modelName: 'text-embedding-3-small',
        vectorStore: 'sqlite_vec',
        vectorDims: 1536,
        indexedChunksCount: 1000,
        ftsEntriesCount: 800,
        lastSyncAt: 1760000000000,
      },
      lastDiagnostic: null,
      isDiagnosing: false,
      reindex: {
        isReindexing: false,
        progressPercent: 0,
        processedChunks: 0,
        totalChunks: 0,
        estimatedTokensUsed: 0,
      },
      isDiagnosticPanelOpen: false,
    };

    const payload: MemoryInspectorEventPayload = {
      action: 'deep_diagnostic',
      timestamp: 1760000002000,
    };

    expect(state.health.status).toBe('ready');
    expect(payload.action).toBe('deep_diagnostic');
  });
});
