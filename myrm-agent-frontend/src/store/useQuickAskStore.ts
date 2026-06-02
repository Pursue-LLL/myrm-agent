import { create } from 'zustand';

interface QuickAskState {
  isOpen: boolean;
  initialText: string;
  openQuickAsk: (text?: string) => void;
  closeQuickAsk: () => void;
}

export const useQuickAskStore = create<QuickAskState>((set) => ({
  isOpen: false,
  initialText: '',
  openQuickAsk: (text = '') => set({ isOpen: true, initialText: text }),
  closeQuickAsk: () => set({ isOpen: false, initialText: '' }),
}));
