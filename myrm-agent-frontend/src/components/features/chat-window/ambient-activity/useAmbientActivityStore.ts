import { create } from 'zustand';
import {
  AmbientDeckSummary,
  BotActivityItem,
  BotActivityStatus,
} from './ambientActivityTypes';
import { aggregateAmbientActivities } from './ambientActivityEngine';

interface AmbientActivityState {
  activities: Record<string, BotActivityItem>;
  isInspectionDrawerOpen: boolean;
  selectedActivityId: string | null;
  isDeckCollapsed: boolean;
  showHiddenBotsInSidebar: boolean;

  recordActivity: (
    params: Omit<BotActivityItem, 'id' | 'timestamp'> & {
      id?: string;
      timestamp?: number;
    },
  ) => string;
  updateActivityStatus: (
    id: string,
    status: BotActivityStatus,
    updates?: Partial<BotActivityItem>,
  ) => void;
  toggleInspectionDrawer: (open?: boolean) => void;
  setSelectedActivity: (id: string | null) => void;
  toggleDeckCollapse: (collapsed?: boolean) => void;
  toggleShowHiddenBots: (show?: boolean) => void;
  getDeckSummary: () => AmbientDeckSummary;
  clear: () => void;
  reset: () => void;
}

let activitySeq = 0;

export const useAmbientActivityStore = create<AmbientActivityState>(
  (set, get) => ({
    activities: {},
    isInspectionDrawerOpen: false,
    selectedActivityId: null,
    isDeckCollapsed: false,
    showHiddenBotsInSidebar: false,

    recordActivity: (params): string => {
      activitySeq += 1;
      const id = params.id ?? `bot-act-${Date.now()}-${activitySeq}`;
      const item: BotActivityItem = {
        id,
        sessionId: params.sessionId,
        sourceAgent: params.sourceAgent,
        targetAgent: params.targetAgent,
        actionSummary: params.actionSummary,
        payloadSnippet: params.payloadSnippet,
        tokenCost: params.tokenCost,
        latencyMs: params.latencyMs,
        status: params.status,
        timestamp: params.timestamp ?? Date.now(),
      };

      set((state) => ({
        activities: {
          ...state.activities,
          [id]: item,
        },
      }));

      return id;
    },

    updateActivityStatus: (
      id: string,
      status: BotActivityStatus,
      updates?: Partial<BotActivityItem>,
    ): void => {
      set((state) => {
        const existing = state.activities[id];
        if (!existing) {
          return state;
        }

        return {
          activities: {
            ...state.activities,
            [id]: {
              ...existing,
              ...updates,
              status,
            },
          },
        };
      });
    },

    toggleInspectionDrawer: (open?: boolean): void => {
      set((state) => ({
        isInspectionDrawerOpen:
          open !== undefined ? open : !state.isInspectionDrawerOpen,
      }));
    },

    setSelectedActivity: (id: string | null): void => {
      set({ selectedActivityId: id });
    },

    toggleDeckCollapse: (collapsed?: boolean): void => {
      set((state) => ({
        isDeckCollapsed:
          collapsed !== undefined ? collapsed : !state.isDeckCollapsed,
      }));
    },

    toggleShowHiddenBots: (show?: boolean): void => {
      set((state) => ({
        showHiddenBotsInSidebar:
          show !== undefined ? show : !state.showHiddenBotsInSidebar,
      }));
    },

    getDeckSummary: (): AmbientDeckSummary => {
      const list = Object.values(get().activities);
      return aggregateAmbientActivities(list);
    },

    clear: (): void => {
      set({
        activities: {},
        selectedActivityId: null,
      });
    },

    reset: (): void => {
      set({
        activities: {},
        isInspectionDrawerOpen: false,
        selectedActivityId: null,
        isDeckCollapsed: false,
        showHiddenBotsInSidebar: false,
      });
    },
  }),
);
