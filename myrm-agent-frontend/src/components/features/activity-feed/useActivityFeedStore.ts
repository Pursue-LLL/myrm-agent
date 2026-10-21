/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/components/features/activity-feed/activityFeedTypes
 *
 * [OUTPUT]
 * - useActivityFeedStore (POS: Reactive state management for multi-system activity feed and auto evaporation)
 *
 * [POS]
 * Central reactive dispatcher for Item 190. Governs live ingestion from email, calendar,
 * messaging, approvals, cron, and kanban, managing smooth automatic evaporation and undoable archives.
 */

import { create } from 'zustand';
import type {
  ActivityFeedItem,
  ActivityFeedFilter,
  ActivityFeedStoreState,
} from './activityFeedTypes';

export interface ActivityFeedStoreActions {
  readonly ingestItem: (item: ActivityFeedItem) => void;
  readonly markAsAutonomousResolved: (id: string, ttlMs?: number) => void;
  readonly evaporateItem: (id: string) => void;
  readonly undoEvaporation: (id: string) => void;
  readonly humanDecide: (id: string, approved: boolean) => void;
  readonly removeItem: (id: string) => void;
  readonly setFilter: (patch: Partial<ActivityFeedFilter>) => void;
  readonly togglePauseEvaporation: (paused?: boolean) => void;
  readonly clearArchive: () => void;
  readonly resetStore: () => void;
}

export type ActivityFeedStore = ActivityFeedStoreState & ActivityFeedStoreActions;

const DEFAULT_FILTER: ActivityFeedFilter = {
  sourceSystem: 'all',
  status: 'all',
  onlyHumanRequired: false,
  searchQuery: '',
};

export const useActivityFeedStore = create<ActivityFeedStore>((set, get) => ({
  items: [],
  archive: [],
  filter: DEFAULT_FILTER,
  isEvaporationPaused: false,

  ingestItem: (item: ActivityFeedItem) => {
    set((state) => {
      const idx = state.items.findIndex((i) => i.id === item.id);
      if (idx >= 0) {
        const next = [...state.items];
        next[idx] = item;
        return { items: next };
      }
      return { items: [item, ...state.items] };
    });
  },

  markAsAutonomousResolved: (id: string, ttlMs: number = 5000) => {
    set((state) => ({
      items: state.items.map((item) => {
        if (item.id === id) {
          return {
            ...item,
            status: 'evaporating',
            resolvedAt: Date.now(),
            evaporationTtlMs: ttlMs,
          };
        }
        return item;
      }),
    }));
  },

  evaporateItem: (id: string) => {
    const item = get().items.find((i) => i.id === id);
    if (!item) {
      return;
    }

    const evaporatedItem: ActivityFeedItem = {
      ...item,
      status: 'evaporated',
      evaporatedAt: Date.now(),
    };

    set((state) => ({
      items: state.items.filter((i) => i.id !== id),
      archive: [evaporatedItem, ...state.archive],
    }));
  },

  undoEvaporation: (id: string) => {
    const item = get().archive.find((i) => i.id === id);
    if (!item) {
      return;
    }

    const restoredItem: ActivityFeedItem = {
      ...item,
      status: 'pending_decision',
      evaporatedAt: undefined,
      resolvedAt: undefined,
    };

    set((state) => ({
      archive: state.archive.filter((i) => i.id !== id),
      items: [restoredItem, ...state.items],
    }));
  },

  humanDecide: (id: string, approved: boolean) => {
    set((state) => ({
      items: state.items.map((item) => {
        if (item.id === id) {
          if (approved) {
            return {
              ...item,
              status: 'evaporating',
              resolvedAt: Date.now(),
              evaporationTtlMs: 3000,
            };
          }
          return {
            ...item,
            status: 'dismissed',
            resolvedAt: Date.now(),
          };
        }
        return item;
      }),
    }));
  },

  removeItem: (id: string) => {
    set((state) => ({
      items: state.items.filter((i) => i.id !== id),
      archive: state.archive.filter((i) => i.id !== id),
    }));
  },

  setFilter: (patch: Partial<ActivityFeedFilter>) => {
    set((state) => ({
      filter: { ...state.filter, ...patch },
    }));
  },

  togglePauseEvaporation: (paused?: boolean) => {
    set((state) => ({
      isEvaporationPaused: typeof paused === 'boolean' ? paused : !state.isEvaporationPaused,
    }));
  },

  clearArchive: () => {
    set({ archive: [] });
  },

  resetStore: () => {
    set({
      items: [],
      archive: [],
      filter: DEFAULT_FILTER,
      isEvaporationPaused: false,
    });
  },
}));
