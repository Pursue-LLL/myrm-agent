/**
 * [INPUT]
 * - @/components/features/chat-window/memory-inspector/memoryInspectorTypes
 *
 * [OUTPUT]
 * - evaluateLatencyRating, calculateReindexTokenEstimate, calculateProgressPercent,
 *   formatVectorStoreLabel, computeSimulatedDiagnostic, dispatchMemoryHealthEvent
 *
 * [POS]
 * Pure computation engine for Item 201 (P1): VisualMemoryReadinessAndVectorHealthInspectorSuite.
 * Evaluates memory readiness latencies, formats vector engine attributes,
 * estimates re-indexing token usage, and dispatches diagnostic events.
 */

import type {
  VectorStoreType,
  LatencyRating,
  DiagnosticLatencyBreakdown,
  MemoryInspectorEventPayload,
} from './memoryInspectorTypes';

export function evaluateLatencyRating(totalMs: number): LatencyRating {
  if (totalMs < 100) {
    return 'optimal';
  }
  if (totalMs <= 300) {
    return 'acceptable';
  }
  return 'degraded';
}

export function calculateReindexTokenEstimate(
  chunkCount: number,
  avgTokensPerChunk = 250,
): number {
  if (chunkCount <= 0) {
    return 0;
  }
  return Math.round(chunkCount * avgTokensPerChunk);
}

export function calculateProgressPercent(processed: number, total: number): number {
  if (total <= 0) {
    return 0;
  }
  const pct = Math.round((processed / total) * 100);
  return Math.min(100, Math.max(0, pct));
}

export function formatVectorStoreLabel(store: VectorStoreType): string {
  switch (store) {
    case 'sqlite_vec': {
      return 'SQLite-vec (本地嵌入向量库)';
    }
    case 'qdrant': {
      return 'Qdrant (分布式向量检索集群)';
    }
    case 'pgvector': {
      return 'PGVector (PostgreSQL 关系向量扩展)';
    }
    case 'memory_ephemeral': {
      return 'Memory Ephemeral (内存临时向量索引)';
    }
    default: {
      return '未知向量引擎';
    }
  }
}

export function computeSimulatedDiagnostic(options?: {
  readonly embeddingDelay?: number;
  readonly storageWriteDelay?: number;
  readonly cosineSearchDelay?: number;
  readonly probedAt?: number;
}): DiagnosticLatencyBreakdown {
  const embeddingMs = options?.embeddingDelay ?? 42;
  const storageWriteMs = options?.storageWriteDelay ?? 12;
  const cosineSearchMs = options?.cosineSearchDelay ?? 16;
  const totalMs = embeddingMs + storageWriteMs + cosineSearchMs;
  const overallRating = evaluateLatencyRating(totalMs);

  return {
    embeddingMs,
    storageWriteMs,
    cosineSearchMs,
    totalMs,
    overallRating,
    probedAt: options?.probedAt ?? Date.now(),
  };
}

export function dispatchMemoryHealthEvent(payload: MemoryInspectorEventPayload): boolean {
  if (typeof window === 'undefined') {
    return false;
  }

  try {
    const event = new CustomEvent('myrm:memory-inspector-diagnostic', {
      detail: payload,
      bubbles: true,
      cancelable: true,
    });
    window.dispatchEvent(event);
    return true;
  } catch {
    return false;
  }
}
