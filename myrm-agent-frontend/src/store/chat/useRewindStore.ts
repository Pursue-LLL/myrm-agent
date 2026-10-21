/**
 * [INPUT]
 * None (Independent UI state store)
 *
 * [OUTPUT]
 * useRewindStore: Zustand store managing singleton active rewind target
 * RewindTarget: chatId, messageId, messageIndex
 *
 * [POS]
 * UI state manager for rewind dialog target. Decouples message action trigger
 * from top-level dialog rendering to maintain stability across chat re-renders.
 */

import { create } from 'zustand';

export interface RewindTarget {
  chatId: string;
  messageId: string;
  messageIndex: number;
}

interface RewindState {
  target: RewindTarget | null;
  openRewind: (target: RewindTarget) => void;
  closeRewind: () => void;
}

export const useRewindStore = create<RewindState>((set) => ({
  target: null,
  openRewind: (target) => set({ target }),
  closeRewind: () => set({ target: null }),
}));
