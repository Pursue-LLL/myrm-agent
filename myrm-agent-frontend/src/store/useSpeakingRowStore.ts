/**
 * [INPUT]
 * - zustand::create (POS: 轻量状态管理)
 *
 * [OUTPUT]
 * - useSpeakingRowStore: the list row whose message is being read aloud, with claim / release actions
 *
 * [POS]
 * Names the message-list row that is voicing its message, so the virtual list keeps that row mounted: read-aloud
 * belongs to the row that started it, and unmounting the row cuts the speech off.
 */
'use client';

import { create } from 'zustand';

interface SpeakingRowState {
  /** Index of the row that is voicing its message; null while nothing is read aloud. */
  rowIndex: number | null;
  claim: (rowIndex: number) => void;
  /**
   * Gives the row up only while it still holds the claim: a row that was taken over by another speaker
   * must not clear its successor's claim when it winds down.
   */
  release: (rowIndex: number) => void;
}

export const useSpeakingRowStore = create<SpeakingRowState>((set) => ({
  rowIndex: null,
  claim: (rowIndex) => set({ rowIndex }),
  release: (rowIndex) => set((state) => (state.rowIndex === rowIndex ? { rowIndex: null } : state)),
}));
