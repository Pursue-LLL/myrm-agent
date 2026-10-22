/**
 * [INPUT]
 * - ./omniReferenceTypes::OmniReferenceState
 * - ./omniReferenceTypes::OmniReferenceItem
 * - ./omniReferenceTypes::ResolvedContextSlice
 * - ./omniReferenceTypes::DimensionFilter
 *
 * [OUTPUT]
 * - useOmniReferenceStore: Zustand store managing autocomplete menu state, search, and slice resolution
 *
 * [POS]
 * Store for Omni-Context @ reference menu.
 * Strictly adheres to 0-any rule and < 400 lines limit.
 */

import { create } from 'zustand';
import type {
  OmniReferenceState,
  OmniReferenceItem,
  ResolvedContextSlice,
  DimensionFilter,
} from './omniReferenceTypes';

export const useOmniReferenceStore = create<OmniReferenceState>((set, get) => ({
  isOpen: false,
  searchQuery: '',
  selectedDimension: 'all',
  selectedIndex: 0,
  items: [],
  isLoading: false,
  error: null,
  activeSlices: {},

  openMenu: (initialQuery = '') => {
    set({
      isOpen: true,
      searchQuery: initialQuery,
      selectedIndex: 0,
      error: null,
    });
    void get().fetchSuggestions(initialQuery, get().selectedDimension);
  },

  closeMenu: () => {
    set({
      isOpen: false,
      searchQuery: '',
      selectedIndex: 0,
      items: [],
      error: null,
      isLoading: false,
    });
  },

  setSearchQuery: (query: string) => {
    set({ searchQuery: query, selectedIndex: 0 });
    void get().fetchSuggestions(query, get().selectedDimension);
  },

  setSelectedDimension: (dimension: DimensionFilter) => {
    set({ selectedDimension: dimension, selectedIndex: 0 });
    void get().fetchSuggestions(get().searchQuery, dimension);
  },

  setSelectedIndex: (index: number) => {
    set({ selectedIndex: index });
  },

  selectNext: () => {
    const { items, selectedIndex } = get();
    if (items.length === 0) {
      return;
    }
    const next = (selectedIndex + 1) % items.length;
    set({ selectedIndex: next });
  },

  selectPrev: () => {
    const { items, selectedIndex } = get();
    if (items.length === 0) {
      return;
    }
    const prev = (selectedIndex - 1 + items.length) % items.length;
    set({ selectedIndex: prev });
  },

  fetchSuggestions: async (query: string, dimension: DimensionFilter = 'all') => {
    set({ isLoading: true, error: null });
    try {
      const params = new URLSearchParams({ q: query });
      if (dimension !== 'all') {
        params.append('dimension', dimension);
      }

      const response = await fetch(`/api/v1/context/reference/search?${params.toString()}`);
      if (!response.ok) {
        throw new Error(`Search failed with status ${response.status}`);
      }

      const json = await response.json();
      const rawList: OmniReferenceItem[] = json?.data || [];

      set({
        items: rawList,
        isLoading: false,
        selectedIndex: 0,
      });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Unknown error';
      set({ error: message, isLoading: false, items: [] });
    }
  },

  resolveSlice: async (item: OmniReferenceItem) => {
    const key = `${item.dimension}:${item.target_id}`;
    const cached = get().activeSlices[key];
    if (cached) {
      return cached;
    }

    try {
      const response = await fetch('/api/v1/context/reference/slice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          dimension: item.dimension,
          target_id: item.target_id,
          label: item.label,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to resolve slice: ${response.status}`);
      }

      const json = await response.json();
      const slice: ResolvedContextSlice = json?.data;
      if (!slice) {
        return null;
      }

      set((state) => ({
        activeSlices: {
          ...state.activeSlices,
          [key]: slice,
        },
      }));

      return slice;
    } catch (err) {
      console.error('Failed to resolve context slice:', err);
      return null;
    }
  },

  clearSlices: () => {
    set({ activeSlices: {} });
  },
}));
