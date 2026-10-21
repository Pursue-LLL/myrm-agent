/**
 * [INPUT]
 * - commandMatrixTypes: CommandCategory, CommandMatrixEntry, CapabilityHintChip, CommandMatrixState
 *
 * [OUTPUT]
 * - useCommandMatrixStore: Zustand state store for command matrix & context suggestions
 *
 * [POS]
 * Client-side state store for Item 38 P0. Strictly under 220 lines. Zero `any`.
 */

import { create } from 'zustand';
import type {
  CapabilityHintChip,
  CommandCategory,
  CommandMatrixEntry,
  CommandMatrixState,
} from './commandMatrixTypes';

const STORAGE_KEY_MASTERED = 'myrm_mastered_commands';

const loadMasteredCommands = (): string[] => {
  if (typeof window === 'undefined') {
    return [];
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY_MASTERED);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as string[]) : [];
  } catch {
    return [];
  }
};

const saveMasteredCommands = (commands: string[]): void => {
  if (typeof window === 'undefined') {
    return;
  }
  try {
    localStorage.setItem(STORAGE_KEY_MASTERED, JSON.stringify(commands));
  } catch {
    // Ignore storage quota errors
  }
};

export const useCommandMatrixStore = create<CommandMatrixState>((set, get) => ({
  isModalOpen: false,
  searchQuery: '',
  selectedCategory: 'all',
  commands: [],
  suggestedChips: [],
  masteredCommands: loadMasteredCommands(),
  selectedIndex: 0,
  isLoading: false,
  error: null,

  openModal: () => {
    set({ isModalOpen: true, selectedIndex: 0 });
    if (get().commands.length === 0) {
      void get().fetchCatalog();
    }
  },

  closeModal: () => {
    set({ isModalOpen: false, searchQuery: '' });
  },

  toggleModal: () => {
    const currentlyOpen = get().isModalOpen;
    if (currentlyOpen) {
      get().closeModal();
    } else {
      get().openModal();
    }
  },

  setSearchQuery: (query: string) => {
    set({ searchQuery: query, selectedIndex: 0 });
  },

  setSelectedCategory: (category: CommandCategory | 'all') => {
    set({ selectedCategory: category, selectedIndex: 0 });
  },

  setSelectedIndex: (index: number) => {
    set({ selectedIndex: index });
  },

  fetchCatalog: async () => {
    set({ isLoading: true, error: null });
    try {
      const res = await fetch('/api/v1/chats/commands/matrix');
      if (!res.ok) {
        throw new Error(`Failed to load command catalog: HTTP ${res.status}`);
      }
      const data = (await res.json()) as { data: { items: CommandMatrixEntry[] } };
      set({ commands: data.data.items, isLoading: false });
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown catalog error';
      set({ isLoading: false, error: msg });
    }
  },

  fetchSuggestions: async (
    sessionId: string,
    status: 'idle' | 'running' | 'paused' | 'interrupted' | 'error',
    runningStepCount: number,
    recentTools: string[],
  ) => {
    try {
      const currentMastered = get().masteredCommands;
      const res = await fetch(`/api/v1/chats/${encodeURIComponent(sessionId)}/commands/suggest`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status,
          running_step_count: runningStepCount,
          recent_tools: recentTools,
          mastered_commands: currentMastered,
          max_results: 3,
        }),
      });
      if (!res.ok) {
        return;
      }
      const data = (await res.json()) as { data: { chips: CapabilityHintChip[] } };
      set({ suggestedChips: data.data.chips });
    } catch {
      // Best-effort heuristic suggestions
    }
  },

  markCommandMastered: (command: string) => {
    const current = get().masteredCommands;
    if (!current.includes(command)) {
      const updated = [...current, command];
      set({
        masteredCommands: updated,
        suggestedChips: get().suggestedChips.filter((c) => c.command !== command),
      });
      saveMasteredCommands(updated);
    }
  },

  dismissChip: (chipId: string, command: string) => {
    get().markCommandMastered(command);
    set({
      suggestedChips: get().suggestedChips.filter((c) => c.chip_id !== chipId),
    });
  },

  reset: () => {
    set({
      isModalOpen: false,
      searchQuery: '',
      selectedCategory: 'all',
      commands: [],
      suggestedChips: [],
      masteredCommands: [],
      selectedIndex: 0,
      isLoading: false,
      error: null,
    });
  },
}));
