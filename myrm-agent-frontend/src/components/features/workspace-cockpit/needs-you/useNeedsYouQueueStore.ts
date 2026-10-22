/**
 * 跨端统一「需要你」中断队列与可锚定后台告警套件 - 响应式状态管理 Store
 *
 * 基于 Zustand 实现通知与台账双写落库、可锚定条目聚焦与批量决策处理。
 */

import { create } from 'zustand';
import type { AnchoredAlert, NeedsYouItem } from './needsYouTypes';
import { buildNeedsYouDeepLink } from './needsYouQueueEngine';

export interface NeedsYouQueueState {
  items: NeedsYouItem[];
  alerts: AnchoredAlert[];
  isDrawerOpen: boolean;
  focusedItemId: string | null;
  selectedItemIds: string[];
  isReasonModalOpen: boolean;
  dismissTargetId: string | null;

  // Actions
  registerInterruption: (
    input: Omit<NeedsYouItem, 'id' | 'createdAt' | 'isDismissed' | 'isHandled' | 'deepLinkUrl'> & {
      id?: string;
      deepLinkUrl?: string;
      createdAt?: number;
    },
  ) => string;
  resolveInterruption: (id: string) => void;
  dismissInterruption: (id: string, reason: string) => void;
  batchResolve: (ids: string[]) => void;
  openDrawer: (focusedId?: string) => void;
  closeDrawer: () => void;
  openReasonModal: (id: string) => void;
  closeReasonModal: () => void;
  toggleSelectItem: (id: string) => void;
  selectAll: () => void;
  deselectAll: () => void;
  markAlertRead: (alertId: string) => void;
  markAllAlertsRead: () => void;
  clearResolvedItems: () => void;
  reset: () => void;
}

export const useNeedsYouQueueStore = create<NeedsYouQueueState>((set, get) => ({
  items: [],
  alerts: [],
  isDrawerOpen: false,
  focusedItemId: null,
  selectedItemIds: [],
  isReasonModalOpen: false,
  dismissTargetId: null,

  registerInterruption: (input) => {
    const id = input.id || `interrupt-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`;
    const now = input.createdAt ?? Date.now();
    const deepLinkUrl =
      input.deepLinkUrl ||
      buildNeedsYouDeepLink(input.chatId, input.messageId, input.turnId, id);

    const newItem: NeedsYouItem = {
      ...input,
      id,
      createdAt: now,
      deepLinkUrl,
      isDismissed: false,
      isHandled: false,
    };

    // 双写机制：同时建立可锚定后台告警记录
    const newAlert: AnchoredAlert = {
      id: `alert-${id}`,
      itemId: id,
      source: input.source,
      title: input.title,
      summary: input.whatWaitingFor,
      timestamp: now,
      hasShownSystemNotification: false,
      isRead: false,
      deepLinkUrl,
    };

    set((state) => ({
      items: [newItem, ...state.items.filter((item) => item.id !== id)],
      alerts: [newAlert, ...state.alerts.filter((alert) => alert.itemId !== id)],
    }));

    return id;
  },

  resolveInterruption: (id: string) => {
    set((state) => ({
      items: state.items.map((item) => {
        if (item.id === id) {
          return { ...item, isHandled: true };
        }
        return item;
      }),
      alerts: state.alerts.map((alert) => {
        if (alert.itemId === id) {
          return { ...alert, isRead: true };
        }
        return alert;
      }),
      selectedItemIds: state.selectedItemIds.filter((itemId) => itemId !== id),
    }));
  },

  dismissInterruption: (id: string, reason: string) => {
    set((state) => ({
      items: state.items.map((item) => {
        if (item.id === id) {
          return {
            ...item,
            isDismissed: true,
            dismissReason: reason,
          };
        }
        return item;
      }),
      alerts: state.alerts.map((alert) => {
        if (alert.itemId === id) {
          return { ...alert, isRead: true };
        }
        return alert;
      }),
      isReasonModalOpen: false,
      dismissTargetId: null,
      selectedItemIds: state.selectedItemIds.filter((itemId) => itemId !== id),
    }));
  },

  batchResolve: (ids: string[]) => {
    const idSet = new Set(ids);
    set((state) => ({
      items: state.items.map((item) => {
        if (idSet.has(item.id)) {
          return { ...item, isHandled: true };
        }
        return item;
      }),
      alerts: state.alerts.map((alert) => {
        if (idSet.has(alert.itemId)) {
          return { ...alert, isRead: true };
        }
        return alert;
      }),
      selectedItemIds: [],
    }));
  },

  openDrawer: (focusedId?: string) => {
    set({
      isDrawerOpen: true,
      focusedItemId: focusedId ?? null,
    });
  },

  closeDrawer: () => {
    set({
      isDrawerOpen: false,
      focusedItemId: null,
      selectedItemIds: [],
    });
  },

  openReasonModal: (id: string) => {
    set({
      isReasonModalOpen: true,
      dismissTargetId: id,
    });
  },

  closeReasonModal: () => {
    set({
      isReasonModalOpen: false,
      dismissTargetId: null,
    });
  },

  toggleSelectItem: (id: string) => {
    set((state) => {
      const isSelected = state.selectedItemIds.includes(id);
      return {
        selectedItemIds: isSelected
          ? state.selectedItemIds.filter((itemId) => itemId !== id)
          : [...state.selectedItemIds, id],
      };
    });
  },

  selectAll: () => {
    const activeIds = get()
      .items.filter((item) => !item.isHandled && !item.isDismissed)
      .map((item) => item.id);
    set({ selectedItemIds: activeIds });
  },

  deselectAll: () => {
    set({ selectedItemIds: [] });
  },

  markAlertRead: (alertId: string) => {
    set((state) => ({
      alerts: state.alerts.map((alert) => {
        if (alert.id === alertId) {
          return { ...alert, isRead: true };
        }
        return alert;
      }),
    }));
  },

  markAllAlertsRead: () => {
    set((state) => ({
      alerts: state.alerts.map((alert) => ({ ...alert, isRead: true })),
    }));
  },

  clearResolvedItems: () => {
    set((state) => ({
      items: state.items.filter((item) => !item.isHandled && !item.isDismissed),
    }));
  },

  reset: () => {
    set({
      items: [],
      alerts: [],
      isDrawerOpen: false,
      focusedItemId: null,
      selectedItemIds: [],
      isReasonModalOpen: false,
      dismissTargetId: null,
    });
  },
}));
