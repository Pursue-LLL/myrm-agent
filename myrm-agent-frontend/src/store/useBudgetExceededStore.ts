'use client';

import { create } from 'zustand';

interface BudgetExceededState {
  open: boolean;
  requiredWu: number | null;
  availableWu: number | null;
  show: (requiredWu: number, availableWu: number) => void;
  close: () => void;
}

export const useBudgetExceededStore = create<BudgetExceededState>((set) => ({
  open: false,
  requiredWu: null,
  availableWu: null,
  show: (requiredWu, availableWu) => set({ open: true, requiredWu, availableWu }),
  close: () => set({ open: false, requiredWu: null, availableWu: null }),
}));
