/**
 * [INPUT] /api/v1/progression
 * [OUTPUT] useProgressionStore: user capability progression state
 * [POS] Manages the user's current level and milestone completion status.
 *       Consumed by SamplePrompts for level-aware prompt selection.
 */

import { create } from 'zustand';

interface MilestoneStatus {
  id: string;
  label: string;
  level: string;
  completed_at: string | null;
}

interface ProgressionState {
  currentLevel: number;
  milestones: MilestoneStatus[];
  initialized: boolean;
}

interface ProgressionActions {
  load: () => Promise<void>;
  markMilestone: (milestoneId: string) => Promise<void>;
}

export const useProgressionStore = create<ProgressionState & ProgressionActions>()(
  (set, get) => ({
    currentLevel: 1,
    milestones: [],
    initialized: false,

    load: async () => {
      try {
        const res = await fetch('/api/v1/progression');
        if (!res.ok) return;
        const data = await res.json();
        set({
          currentLevel: data.current_level ?? 1,
          milestones: data.milestones ?? [],
          initialized: true,
        });
      } catch (e) {
        console.warn('Failed to load progression:', e);
      }
    },

    markMilestone: async (milestoneId: string) => {
      try {
        const res = await fetch(`/api/v1/progression/${milestoneId}`, {
          method: 'PATCH',
        });
        if (!res.ok) return;
        const data = await res.json();
        const prev = get();
        const updated = prev.milestones.map((m) =>
          m.id === milestoneId ? { ...m, completed_at: data.completed_at } : m,
        );
        set({ currentLevel: data.current_level, milestones: updated });
      } catch (e) {
        console.warn('Failed to mark milestone:', e);
      }
    },
  }),
);
