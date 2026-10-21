/**
 * 安静时刻「有更新可用」CTA 编排套件 - 响应式状态管理 Store
 *
 * 基于 Zustand 实现安静时刻上下文追踪、快照缓存复用、版本忽略记忆与代际自愈重置。
 */

import { create } from 'zustand';
import type {
  ConnectionMode,
  DismissedVersionRecord,
  QuietMomentContext,
  UpdateAvailabilitySnapshot,
} from './quietMomentUpdateTypes';
import {
  DEFAULT_TYPING_GRACE_MS,
  evaluateUpdateOfferEligibility,
  validateActionContext,
} from './quietMomentUpdateEngine';

export interface QuietMomentUpdateState {
  generation: number;
  snapshot: UpdateAvailabilitySnapshot | null;
  isOfferVisible: boolean;
  activeTipId: string | null;
  lastOfferedAt: number | undefined;
  dismissedVersions: DismissedVersionRecord[];
  isDismissModalOpen: boolean;

  // 上下文监控参数
  lastTypedAt: number;
  typingGraceMs: number;
  isWindowFocused: boolean;
  isDocumentVisible: boolean;
  hasActiveStreamingOrTask: boolean;
  hasBlockingSurface: boolean;
  connectionMode: ConnectionMode;
  isInstallingBusy: boolean;

  // Actions
  noteTyping: (now?: number) => void;
  setWindowFocus: (focused: boolean) => void;
  setDocumentVisibility: (visible: boolean) => void;
  setTaskBusy: (busy: boolean) => void;
  setBlockingSurface: (active: boolean) => void;
  setInstallingBusy: (busy: boolean) => void;
  setConnectionMode: (mode: ConnectionMode) => void;
  setSnapshot: (snapshot: UpdateAvailabilitySnapshot | null) => void;
  openDismissModal: () => void;
  closeDismissModal: () => void;
  dismissVersion: (version: string, remindHours?: number, now?: number) => void;
  restoreVersion: (version: string) => void;
  closeOffer: () => void;
  checkQuietMoment: (nowOverride?: number) => boolean;
  executeAction: (onProceed: () => void | Promise<void>) => Promise<boolean>;
  reset: () => void;
}

export const useQuietMomentUpdateStore = create<QuietMomentUpdateState>((set, get) => ({
  generation: 1,
  snapshot: null,
  isOfferVisible: false,
  activeTipId: null,
  lastOfferedAt: undefined,
  dismissedVersions: [],
  isDismissModalOpen: false,

  lastTypedAt: 0,
  typingGraceMs: DEFAULT_TYPING_GRACE_MS,
  isWindowFocused: true,
  isDocumentVisible: true,
  hasActiveStreamingOrTask: false,
  hasBlockingSurface: false,
  connectionMode: 'local',
  isInstallingBusy: false,

  noteTyping: (now?: number) => {
    set({ lastTypedAt: now ?? Date.now() });
  },

  setWindowFocus: (focused: boolean) => {
    set({ isWindowFocused: focused });
  },

  setDocumentVisibility: (visible: boolean) => {
    set({ isDocumentVisible: visible });
  },

  setTaskBusy: (busy: boolean) => {
    set({ hasActiveStreamingOrTask: busy });
  },

  setBlockingSurface: (active: boolean) => {
    set({ hasBlockingSurface: active });
  },

  setInstallingBusy: (busy: boolean) => {
    set({ isInstallingBusy: busy });
    if (busy) {
      set({ isOfferVisible: false });
    }
  },

  setConnectionMode: (mode: ConnectionMode) => {
    const currentMode = get().connectionMode;
    if (currentMode !== mode) {
      // 跨网络/网关切换时世代递增并即刻注销先前就绪的旧提示，防止网络上下文错乱
      set((state) => ({
        generation: state.generation + 1,
        connectionMode: mode,
        snapshot: null,
        isOfferVisible: false,
        activeTipId: null,
      }));
    }
  },

  setSnapshot: (snapshot: UpdateAvailabilitySnapshot | null) => {
    set({ snapshot });
  },

  openDismissModal: () => {
    set({ isDismissModalOpen: true });
  },

  closeDismissModal: () => {
    set({ isDismissModalOpen: false });
  },

  dismissVersion: (version: string, remindHours?: number, now?: number) => {
    const currentTime = now ?? Date.now();
    const remindAfter = remindHours ? currentTime + remindHours * 3_600_000 : undefined;
    const newRecord: DismissedVersionRecord = {
      version,
      dismissedAt: currentTime,
      remindAfter,
    };

    set((state) => ({
      dismissedVersions: [
        ...state.dismissedVersions.filter((r) => r.version !== version),
        newRecord,
      ],
      isOfferVisible: false,
      activeTipId: null,
      isDismissModalOpen: false,
    }));
  },

  restoreVersion: (version: string) => {
    set((state) => ({
      dismissedVersions: state.dismissedVersions.filter((r) => r.version !== version),
    }));
  },

  closeOffer: () => {
    set({ isOfferVisible: false, activeTipId: null });
  },

  checkQuietMoment: (nowOverride?: number) => {
    const state = get();
    const now = nowOverride ?? Date.now();

    const ctx: QuietMomentContext = {
      isWindowFocused: state.isWindowFocused,
      isDocumentVisible: state.isDocumentVisible,
      lastTypedAt: state.lastTypedAt,
      typingGraceMs: state.typingGraceMs,
      hasActiveStreamingOrTask: state.hasActiveStreamingOrTask,
      hasBlockingSurface: state.hasBlockingSurface,
      connectionMode: state.connectionMode,
      isInstallingBusy: state.isInstallingBusy,
      now,
    };

    const eligibility = evaluateUpdateOfferEligibility({
      ctx,
      snapshot: state.snapshot,
      dismissedRecords: state.dismissedVersions,
      lastOfferedAt: state.lastOfferedAt,
    });

    if (eligibility.canOffer) {
      set({
        isOfferVisible: true,
        activeTipId: eligibility.tipId ?? `update-offer:${state.snapshot?.version ?? 'latest'}`,
        lastOfferedAt: now,
      });
      return true;
    }

    return false;
  },

  executeAction: async (onProceed: () => void | Promise<void>) => {
    const state = get();
    const expectedGeneration = state.generation;
    const now = Date.now();

    const ctx: QuietMomentContext = {
      isWindowFocused: state.isWindowFocused,
      isDocumentVisible: state.isDocumentVisible,
      lastTypedAt: state.lastTypedAt,
      typingGraceMs: state.typingGraceMs,
      hasActiveStreamingOrTask: state.hasActiveStreamingOrTask,
      hasBlockingSurface: state.hasBlockingSurface,
      connectionMode: state.connectionMode,
      isInstallingBusy: state.isInstallingBusy,
      now,
    };

    const isValid = validateActionContext(expectedGeneration, state.generation, ctx);
    if (!isValid) {
      set({ isOfferVisible: false, activeTipId: null });
      return false;
    }

    set({ isOfferVisible: false, activeTipId: null });
    await onProceed();
    return true;
  },

  reset: () => {
    set((state) => ({
      generation: state.generation + 1,
      snapshot: null,
      isOfferVisible: false,
      activeTipId: null,
      isDismissModalOpen: false,
    }));
  },
}));
