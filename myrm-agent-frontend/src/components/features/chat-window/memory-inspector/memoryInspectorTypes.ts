/**
 * [INPUT]
 * - None (Pure domain type definitions for Visual Memory Readiness & Vector Health Inspector)
 *
 * [OUTPUT]
 * - MemoryProviderStatus, VectorStoreType, LatencyRating, MemoryEngineHealth,
 *   DiagnosticLatencyBreakdown, ReindexProgress, MemoryInspectorStoreState
 *
 * [POS]
 * Unified contracts for Item 201 (P1): VisualMemoryReadinessAndVectorHealthInspectorSuite.
 * Powers GUI-facing white-box memory status inspection, one-click deep latency probing,
 * and force re-indexing progress visualization.
 */

export type MemoryProviderStatus = 'ready' | 'degraded' | 'error' | 'testing';

export type VectorStoreType = 'sqlite_vec' | 'qdrant' | 'pgvector' | 'memory_ephemeral';

export type LatencyRating = 'optimal' | 'acceptable' | 'degraded';

export interface MemoryEngineHealth {
  readonly provider: string;
  readonly status: MemoryProviderStatus;
  readonly modelName: string;
  readonly vectorStore: VectorStoreType;
  readonly vectorDims: number;
  readonly indexedChunksCount: number;
  readonly ftsEntriesCount: number;
  readonly lastSyncAt: number;
  readonly errorMessage?: string;
}

export interface DiagnosticLatencyBreakdown {
  readonly embeddingMs: number;
  readonly storageWriteMs: number;
  readonly cosineSearchMs: number;
  readonly totalMs: number;
  readonly overallRating: LatencyRating;
  readonly probedAt: number;
}

export interface ReindexProgress {
  readonly isReindexing: boolean;
  readonly progressPercent: number;
  readonly processedChunks: number;
  readonly totalChunks: number;
  readonly estimatedTokensUsed: number;
}

export interface MemoryInspectorEventPayload {
  readonly action: 'deep_diagnostic' | 'reindex_start' | 'reindex_progress' | 'reindex_complete';
  readonly diagnostic?: DiagnosticLatencyBreakdown;
  readonly progress?: ReindexProgress;
  readonly timestamp: number;
}

export interface MemoryInspectorStoreState {
  readonly health: MemoryEngineHealth;
  readonly lastDiagnostic: DiagnosticLatencyBreakdown | null;
  readonly isDiagnosing: boolean;
  readonly reindex: ReindexProgress;
  readonly isDiagnosticPanelOpen: boolean;
}
