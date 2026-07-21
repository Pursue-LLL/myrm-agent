'use client';

import { create } from 'zustand';
import { useBudgetExceededStore } from '@/store/useBudgetExceededStore';

export type NudgeTrigger = 'low_balance' | 'feature_gate';

interface UpgradeNudgeState {
  open: boolean;
  trigger: NudgeTrigger | null;
  blockedFeature: string | null;
  showLowBalance: (balanceWu: number, monthlyWu: number) => void;
  showFeatureGate: (feature: string) => void;
  close: () => void;
}

const STORAGE_KEY = 'upgrade_nudge_dismissed_at';
const DISMISS_COOLDOWN_MS = 24 * 60 * 60 * 1000;

function isDismissedRecently(): boolean {
  if (typeof window === 'undefined') return true;
  const raw = localStorage.getItem(STORAGE_KEY);
  if (!raw) return false;
  const ts = parseInt(raw, 10);
  return Date.now() - ts < DISMISS_COOLDOWN_MS;
}

function isBudgetExceededOpen(): boolean {
  return useBudgetExceededStore.getState().open;
}

export const useUpgradeNudgeStore = create<UpgradeNudgeState>((set) => ({
  open: false,
  trigger: null,
  blockedFeature: null,

  showLowBalance: (_balanceWu, _monthlyWu) => {
    if (isDismissedRecently() || isBudgetExceededOpen()) return;
    set({ open: true, trigger: 'low_balance', blockedFeature: null });
  },

  showFeatureGate: (feature) => {
    if (isBudgetExceededOpen()) return;
    set({ open: true, trigger: 'feature_gate', blockedFeature: feature });
  },

  close: () => {
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY, String(Date.now()));
    }
    set({ open: false, trigger: null, blockedFeature: null });
  },
}));
