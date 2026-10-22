/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/components/features/chat-window/context-hud/contextHudTypes
 * - @/components/features/chat-window/context-hud/contextHudEngine
 *
 * [OUTPUT]
 * - useContextHudStore (POS: Central reactive store for context telemetry & cache attribution)
 *
 * [POS]
 * Central reactive dispatcher for Item 195 (P1): ContextWatermarkAndCacheAttributionHudSuite.
 * Manages 6-metric telemetry per chat session, watermark warnings, and cache diagnostics.
 */

import { create } from 'zustand';
import type {
  AutoCompactState,
  ContextHudMetrics,
  CacheAttributionReport,
  ContextHudStoreState,
} from './contextHudTypes';
import {
  computeContextHudMetrics,
  diagnoseCacheMiss,
} from './contextHudEngine';

export interface ContextHudStoreActions {
  readonly updateMetrics: (
    chatId: string,
    params: {
      inputTokens: number;
      outputTokens: number;
      cachedReadTokens: number;
      contextLimit?: number;
      autoCompactState?: AutoCompactState;
      turnIndex?: number;
      hasDynamicTime?: boolean;
      hasToolMutation?: boolean;
      hasSystemPromptChanged?: boolean;
    },
  ) => void;
  readonly setActiveChatId: (chatId: string | null) => void;
  readonly togglePopover: (open?: boolean) => void;
  readonly clearChatMetrics: (chatId: string) => void;
  readonly triggerAutoCompact: (chatId: string) => void;
  readonly resetStore: () => void;
}

export type ContextHudStore = ContextHudStoreState & ContextHudStoreActions;

const initialDefaultMetrics: ContextHudMetrics = computeContextHudMetrics({
  inputTokens: 0,
  outputTokens: 0,
  cachedReadTokens: 0,
});

const initialState: ContextHudStoreState = {
  metricsByChatId: {},
  attributionReports: {},
  activeChatId: null,
  isPopoverOpen: false,
};

export const useContextHudStore = create<ContextHudStore>((set, get) => ({
  ...initialState,

  updateMetrics: (chatId, params) => {
    const metrics = computeContextHudMetrics(params);
    const attribution = diagnoseCacheMiss({
      inputTokens: params.inputTokens,
      cachedReadTokens: params.cachedReadTokens,
      turnIndex: params.turnIndex ?? 2,
      hasDynamicTime: params.hasDynamicTime,
      hasToolMutation: params.hasToolMutation,
      hasSystemPromptChanged: params.hasSystemPromptChanged,
    });

    set((state) => ({
      metricsByChatId: {
        ...state.metricsByChatId,
        [chatId]: metrics,
      },
      attributionReports: {
        ...state.attributionReports,
        [chatId]: attribution,
      },
    }));
  },

  setActiveChatId: (chatId) => {
    set({ activeChatId: chatId });
  },

  togglePopover: (open) => {
    set((state) => ({
      isPopoverOpen: typeof open === 'boolean' ? open : !state.isPopoverOpen,
    }));
  },

  clearChatMetrics: (chatId) => {
    set((state) => {
      const nextMetrics = { ...state.metricsByChatId };
      const nextReports = { ...state.attributionReports };
      delete nextMetrics[chatId];
      delete nextReports[chatId];
      return {
        metricsByChatId: nextMetrics,
        attributionReports: nextReports,
      };
    });
  },

  triggerAutoCompact: (chatId) => {
    const current = get().metricsByChatId[chatId] ?? initialDefaultMetrics;
    const compactedInput = Math.round(current.inputTokens * 0.6);
    const updatedMetrics = computeContextHudMetrics({
      inputTokens: compactedInput,
      outputTokens: current.outputTokens,
      cachedReadTokens: Math.min(compactedInput, current.cachedReadTokens),
      contextLimit: current.contextLimit,
      autoCompactState: 'active',
    });

    set((state) => ({
      metricsByChatId: {
        ...state.metricsByChatId,
        [chatId]: updatedMetrics,
      },
    }));
  },

  resetStore: () => {
    set({ ...initialState });
  },
}));
