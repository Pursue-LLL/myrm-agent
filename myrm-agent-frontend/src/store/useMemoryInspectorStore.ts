/**
 * Zustand Store for Memory Inspector & Epistemic Governance Drawer.
 *
 * [INPUT] EpistemicMemoryItem, EpistemicTier
 * [OUTPUT] useMemoryInspectorStore hook
 * [POS] Item 30 global memory governance state manager. Strictly under 160 lines. Zero `any`.
 */

import { create } from 'zustand';
import type { EpistemicMemoryItem, EpistemicTier } from '@/components/features/memory-inspector/memoryInspectorTypes';

interface MemoryInspectorState {
  isOpen: boolean;
  sessionId: string;
  memories: EpistemicMemoryItem[];
  selectedMemoryId: string | null;
  openInspector: (sessionId: string, memories?: EpistemicMemoryItem[]) => void;
  closeInspector: () => void;
  selectMemory: (memoryId: string | null) => void;
  promoteMemory: (memoryId: string, targetTier?: 'assertion' | 'observation') => Promise<void>;
  correctMemory: (memoryId: string, newContent: string) => Promise<void>;
  forgetMemory: (memoryId: string) => Promise<void>;
}

export const useMemoryInspectorStore = create<MemoryInspectorState>((set, get) => ({
  isOpen: false,
  sessionId: '',
  memories: [],
  selectedMemoryId: null,

  openInspector: (sessionId, memories = []) => {
    set({
      isOpen: true,
      sessionId,
      memories,
      selectedMemoryId: memories[0]?.id ?? null,
    });
  },

  closeInspector: () => {
    set({
      isOpen: false,
      selectedMemoryId: null,
    });
  },

  selectMemory: (memoryId) => {
    set({ selectedMemoryId: memoryId });
  },

  promoteMemory: async (memoryId, targetTier = 'assertion') => {
    // Atomically upgrade epistemic tier in memory list
    set((state) => ({
      memories: state.memories.map((m) => {
        if (m.id !== memoryId) return m;
        const newScore = targetTier === 'assertion' ? 1.0 : 0.85;
        const newProvenance = [...m.provenance_chain, `operator_promoted_to_${targetTier}`];
        return {
          ...m,
          epistemic_tier: targetTier as EpistemicTier,
          confidence_score: newScore,
          provenance_chain: newProvenance,
        };
      }),
    }));
  },

  correctMemory: async (memoryId, newContent) => {
    // Atomically update text content in-place
    set((state) => ({
      memories: state.memories.map((m) => {
        if (m.id !== memoryId) return m;
        const newProvenance = [...m.provenance_chain, 'operator_in_place_corrected'];
        return {
          ...m,
          content: newContent,
          provenance_chain: newProvenance,
        };
      }),
    }));
  },

  forgetMemory: async (memoryId) => {
    // Physically erase memory from state
    set((state) => {
      const remaining = state.memories.filter((m) => m.id !== memoryId);
      return {
        memories: remaining,
        selectedMemoryId: state.selectedMemoryId === memoryId ? remaining[0]?.id ?? null : state.selectedMemoryId,
      };
    });
  },
}));
