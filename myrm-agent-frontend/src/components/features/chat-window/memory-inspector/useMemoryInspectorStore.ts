/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/components/features/chat-window/memory-inspector/memoryInspectorTypes
 * - @/components/features/chat-window/memory-inspector/memoryInspectorEngine
 *
 * [OUTPUT]
 * - useMemoryInspectorStore (POS: Central reactive store for memory health inspector and re-indexer)
 *
 * [POS]
 * Central reactive dispatcher for Item 201 (P1): VisualMemoryReadinessAndVectorHealthInspectorSuite.
 * Manages memory engine readiness attributes, deep latency diagnostics, and force re-indexing workflows.
 */

import { create } from 'zustand';
import type {
  MemoryInspectorStoreState,
  MemoryEngineHealth,
  DiagnosticLatencyBreakdown,
} from './memoryInspectorTypes';
import {
  calculateProgressPercent,
  calculateReindexTokenEstimate,
  computeSimulatedDiagnostic,
  dispatchMemoryHealthEvent,
} from './memoryInspectorEngine';

export interface MemoryInspectorStoreActions {
  readonly setEngineHealth: (health: Partial<MemoryEngineHealth>) => void;
  readonly runDeepDiagnostic: (options?: {
    readonly embeddingDelay?: number;
    readonly storageWriteDelay?: number;
    readonly cosineSearchDelay?: number;
  }) => Promise<DiagnosticLatencyBreakdown>;
  readonly startReindexing: (totalChunks?: number) => void;
  readonly updateReindexProgress: (processedChunks: number) => void;
  readonly completeReindexing: () => void;
  readonly cancelReindexing: () => void;
  readonly toggleDiagnosticPanel: (open?: boolean) => void;
  readonly resetStore: () => void;
}

export type MemoryInspectorStore = MemoryInspectorStoreState & MemoryInspectorStoreActions;

const defaultHealth: MemoryEngineHealth = {
  provider: 'openai',
  status: 'ready',
  modelName: 'text-embedding-3-small',
  vectorStore: 'sqlite_vec',
  vectorDims: 1536,
  indexedChunksCount: 4280,
  ftsEntriesCount: 3950,
  lastSyncAt: 1760000000000,
};

const initialState: MemoryInspectorStoreState = {
  health: defaultHealth,
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

export const useMemoryInspectorStore = create<MemoryInspectorStore>((set, get) => ({
  ...initialState,

  setEngineHealth: (partialHealth) => {
    set((state) => ({
      health: {
        ...state.health,
        ...partialHealth,
      },
    }));
  },

  runDeepDiagnostic: async (options) => {
    set({ isDiagnosing: true });

    // 模拟轻量探针往返
    await new Promise((resolve) => setTimeout(resolve, 50));

    const diagnostic = computeSimulatedDiagnostic(options);

    dispatchMemoryHealthEvent({
      action: 'deep_diagnostic',
      diagnostic,
      timestamp: Date.now(),
    });

    set((state) => ({
      isDiagnosing: false,
      lastDiagnostic: diagnostic,
      isDiagnosticPanelOpen: true,
      health: {
        ...state.health,
        lastSyncAt: Date.now(),
      },
    }));

    return diagnostic;
  },

  startReindexing: (totalChunksOverride) => {
    const total = totalChunksOverride ?? get().health.indexedChunksCount;
    const initialProgress = {
      isReindexing: true,
      progressPercent: 0,
      processedChunks: 0,
      totalChunks: total,
      estimatedTokensUsed: 0,
    };

    dispatchMemoryHealthEvent({
      action: 'reindex_start',
      progress: initialProgress,
      timestamp: Date.now(),
    });

    set({ reindex: initialProgress });
  },

  updateReindexProgress: (processedChunks: number) => {
    const { totalChunks } = get().reindex;
    const progressPercent = calculateProgressPercent(processedChunks, totalChunks);
    const estimatedTokensUsed = calculateReindexTokenEstimate(processedChunks);

    const progress = {
      isReindexing: progressPercent < 100,
      progressPercent,
      processedChunks,
      totalChunks,
      estimatedTokensUsed,
    };

    dispatchMemoryHealthEvent({
      action: progressPercent >= 100 ? 'reindex_complete' : 'reindex_progress',
      progress,
      timestamp: Date.now(),
    });

    set({ reindex: progress });
  },

  completeReindexing: () => {
    const { totalChunks } = get().reindex;
    const completedProgress = {
      isReindexing: false,
      progressPercent: 100,
      processedChunks: totalChunks,
      totalChunks,
      estimatedTokensUsed: calculateReindexTokenEstimate(totalChunks),
    };

    dispatchMemoryHealthEvent({
      action: 'reindex_complete',
      progress: completedProgress,
      timestamp: Date.now(),
    });

    set({ reindex: completedProgress });
  },

  cancelReindexing: () => {
    set({
      reindex: {
        isReindexing: false,
        progressPercent: 0,
        processedChunks: 0,
        totalChunks: 0,
        estimatedTokensUsed: 0,
      },
    });
  },

  toggleDiagnosticPanel: (open) => {
    set((state) => ({
      isDiagnosticPanelOpen:
        typeof open === 'boolean' ? open : !state.isDiagnosticPanelOpen,
    }));
  },

  resetStore: () => {
    set({ ...initialState });
  },
}));
