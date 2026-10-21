/**
 * [INPUT]
 * - zustand (POS: Global reactive store)
 * - @/components/features/chat-window/final-card/finalCardTypes
 *
 * [OUTPUT]
 * - useFinalCardStore (POS: Reactive store for Terminal-Free Final Card Presentation Contract)
 *
 * [POS]
 * Central reactive dispatcher for Item 192 (P0).
 * Stores presentation contracts keyed by card ID and manages transcript modal states.
 */

import { create } from 'zustand';
import type {
  FinalCardPresentationContract,
  FinalCardStoreState,
} from './finalCardTypes';

export interface FinalCardStoreActions {
  readonly upsertCard: (card: FinalCardPresentationContract) => void;
  readonly removeCard: (cardId: string) => void;
  readonly clearCards: () => void;
  readonly openTranscriptModal: (cardId: string) => void;
  readonly closeTranscriptModal: () => void;
  readonly getCardByTurnId: (turnId: string) => FinalCardPresentationContract | undefined;
  readonly resetStore: () => void;
}

export type FinalCardStore = FinalCardStoreState & FinalCardStoreActions;

const initialState: FinalCardStoreState = {
  cards: {},
  activeTranscriptCardId: null,
};

export const useFinalCardStore = create<FinalCardStore>((set, get) => ({
  ...initialState,

  upsertCard: (card: FinalCardPresentationContract) => {
    set((state) => ({
      cards: {
        ...state.cards,
        [card.id]: card,
      },
    }));
  },

  removeCard: (cardId: string) => {
    set((state) => {
      const nextCards = { ...state.cards };
      delete nextCards[cardId];
      return {
        cards: nextCards,
        activeTranscriptCardId:
          state.activeTranscriptCardId === cardId ? null : state.activeTranscriptCardId,
      };
    });
  },

  clearCards: () => {
    set({
      cards: {},
      activeTranscriptCardId: null,
    });
  },

  openTranscriptModal: (cardId: string) => {
    set({
      activeTranscriptCardId: cardId,
    });
  },

  closeTranscriptModal: () => {
    set({
      activeTranscriptCardId: null,
    });
  },

  getCardByTurnId: (turnId: string) => {
    const cards = Object.values(get().cards);
    return cards.find((card) => card.turnId === turnId);
  },

  resetStore: () => {
    set({ ...initialState });
  },
}));
