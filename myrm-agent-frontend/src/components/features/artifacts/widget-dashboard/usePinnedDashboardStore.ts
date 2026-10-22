/**
 * [INPUT]
 * - widgetDashboardTypes: PinnedWidget, WidgetNetworkPolicy
 *
 * [OUTPUT]
 * - usePinnedDashboardStore: Zustand store for pinned interactive widgets and dashboard drawer
 *
 * [POS]
 * Store for managing pinned widgets, network policies, and poster exports (Item 48 P0).
 * Strictly under 150 lines. Zero `any`.
 */

import { create } from 'zustand';
import type { PinnedWidget, WidgetNetworkPolicy } from './widgetDashboardTypes';

interface PinnedDashboardState {
  pinnedWidgets: PinnedWidget[];
  isDrawerOpen: boolean;
  activeExportWidget: PinnedWidget | null;

  pinWidget: (widget: Omit<PinnedWidget, 'pinnedAt'>) => void;
  unpinWidget: (artifactId: string) => void;
  togglePin: (widget: Omit<PinnedWidget, 'pinnedAt'>) => boolean;
  isPinned: (artifactId: string) => boolean;
  setNetworkPolicy: (artifactId: string, policy: WidgetNetworkPolicy) => void;
  setDrawerOpen: (isOpen: boolean) => void;
  setActiveExportWidget: (widget: PinnedWidget | null) => void;
  clearAllPins: () => void;
}

export const usePinnedDashboardStore = create<PinnedDashboardState>((set, get) => ({
  pinnedWidgets: [],
  isDrawerOpen: false,
  activeExportWidget: null,

  pinWidget: (widget) => {
    const existing = get().pinnedWidgets.find((w) => w.artifactId === widget.artifactId);
    if (existing) {
      return;
    }
    const newWidget: PinnedWidget = {
      ...widget,
      pinnedAt: Date.now(),
    };
    set((state) => ({
      pinnedWidgets: [newWidget, ...state.pinnedWidgets],
    }));
  },

  unpinWidget: (artifactId: string) => {
    set((state) => ({
      pinnedWidgets: state.pinnedWidgets.filter((w) => w.artifactId !== artifactId),
      activeExportWidget:
        state.activeExportWidget?.artifactId === artifactId
          ? null
          : state.activeExportWidget,
    }));
  },

  togglePin: (widget) => {
    const isCurrentlyPinned = get().isPinned(widget.artifactId);
    if (isCurrentlyPinned) {
      get().unpinWidget(widget.artifactId);
      return false;
    }
    get().pinWidget(widget);
    return true;
  },

  isPinned: (artifactId: string) => {
    return get().pinnedWidgets.some((w) => w.artifactId === artifactId);
  },

  setNetworkPolicy: (artifactId: string, policy: WidgetNetworkPolicy) => {
    set((state) => ({
      pinnedWidgets: state.pinnedWidgets.map((w) => {
        if (w.artifactId === artifactId) {
          return { ...w, networkPolicy: policy };
        }
        return w;
      }),
    }));
  },

  setDrawerOpen: (isOpen: boolean) => {
    set({ isDrawerOpen: isOpen });
  },

  setActiveExportWidget: (widget: PinnedWidget | null) => {
    set({ activeExportWidget: widget });
  },

  clearAllPins: () => {
    set({
      pinnedWidgets: [],
      activeExportWidget: null,
    });
  },
}));
