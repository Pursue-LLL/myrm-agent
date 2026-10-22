/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/components/features/sidebar/attention-hub/attentionHubTypes
 * - @/components/features/sidebar/attention-hub/attentionHubEngine
 *
 * [OUTPUT]
 * - useAttentionHubStore (POS: Reactive state management for Attention Hub & Interventions)
 *
 * [POS]
 * Central reactive dispatcher for Item 189. Manages live cross-session attention alerts,
 * handles batch clears for resolved tasks, and orchestrates smooth focus shuttles.
 */

import { create } from 'zustand';
import type {
  AttentionItem,
  AttentionCategory,
  AttentionFilterState,
  AttentionHubStoreState,
} from './attentionHubTypes';
import { generateAnchorElementId, performSmoothShuttle } from './attentionHubEngine';

export interface AttentionHubStoreActions {
  readonly upsertItem: (item: AttentionItem) => void;
  readonly removeItem: (id: string) => void;
  readonly markAsRead: (id: string) => void;
  readonly markAllAsRead: () => void;
  readonly batchClearResolved: () => void;
  readonly togglePanel: (open?: boolean) => void;
  readonly setCategoryFilter: (category: AttentionCategory | 'all') => void;
  readonly setSearchQuery: (query: string) => void;
  readonly setOnlyActionRequired: (only: boolean) => void;
  readonly shuttleToTarget: (
    itemId: string,
    onNavigateToChat?: (chatId: string) => void,
  ) => boolean;
  readonly resetStore: () => void;
}

export type AttentionHubStore = AttentionHubStoreState & AttentionHubStoreActions;

const DEFAULT_FILTER: AttentionFilterState = {
  category: 'all',
  onlyActionRequired: false,
  searchQuery: '',
};

export const useAttentionHubStore = create<AttentionHubStore>((set, get) => ({
  items: [],
  isPanelOpen: false,
  filter: DEFAULT_FILTER,

  upsertItem: (item: AttentionItem) => {
    set((state) => {
      const existingIndex = state.items.findIndex((i) => i.id === item.id);
      if (existingIndex >= 0) {
        const next = [...state.items];
        next[existingIndex] = item;
        return { items: next };
      }
      return { items: [item, ...state.items] };
    });
  },

  removeItem: (id: string) => {
    set((state) => ({
      items: state.items.filter((i) => i.id !== id),
    }));
  },

  markAsRead: (id: string) => {
    set((state) => ({
      items: state.items.map((i) => (i.id === id ? { ...i, isRead: true } : i)),
    }));
  },

  markAllAsRead: () => {
    set((state) => ({
      items: state.items.map((i) => ({ ...i, isRead: true })),
    }));
  },

  batchClearResolved: () => {
    set((state) => ({
      items: state.items.filter((i) => i.actionRequired),
    }));
  },

  togglePanel: (open?: boolean) => {
    set((state) => ({
      isPanelOpen: typeof open === 'boolean' ? open : !state.isPanelOpen,
    }));
  },

  setCategoryFilter: (category: AttentionCategory | 'all') => {
    set((state) => ({
      filter: { ...state.filter, category },
    }));
  },

  setSearchQuery: (searchQuery: string) => {
    set((state) => ({
      filter: { ...state.filter, searchQuery },
    }));
  },

  setOnlyActionRequired: (onlyActionRequired: boolean) => {
    set((state) => ({
      filter: { ...state.filter, onlyActionRequired },
    }));
  },

  shuttleToTarget: (itemId: string, onNavigateToChat?: (chatId: string) => void): boolean => {
    const item = get().items.find((i) => i.id === itemId);
    if (!item) {
      return false;
    }

    // Mark item as read upon focus shuttle
    get().markAsRead(itemId);

    if (onNavigateToChat) {
      onNavigateToChat(item.chatId);
    }

    const anchorId = generateAnchorElementId(item.chatId, item.targetAnchorNodeId);
    return performSmoothShuttle(anchorId);
  },

  resetStore: () => {
    set({
      items: [],
      isPanelOpen: false,
      filter: DEFAULT_FILTER,
    });
  },
}));
