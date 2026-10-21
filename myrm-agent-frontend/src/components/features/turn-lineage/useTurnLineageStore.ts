import { create } from 'zustand';
import {
  ChatTurnItem,
  LineageFilterMode,
} from './turnLineageTypes';
import {
  getDefaultTurns,
  traceCausalityLineage,
} from './turnLineageEngine';

interface TurnLineageState {
  turns: ChatTurnItem[];
  filterMode: LineageFilterMode;
  activeTurnId: string | null;
  highlightedLineageChain: string[];
  hoveredTurnId: string | null;
  isRailExpanded: boolean;

  setTurns: (turns: ChatTurnItem[]) => void;
  setFilterMode: (mode: LineageFilterMode) => void;
  selectTurn: (turnId: string | null) => void;
  setHoveredTurnId: (turnId: string | null) => void;
  toggleRailExpanded: () => void;
  resetStore: () => void;
}

export const useTurnLineageStore = create<TurnLineageState>((set, get) => ({
  turns: getDefaultTurns(),
  filterMode: 'all',
  activeTurnId: null,
  highlightedLineageChain: [],
  hoveredTurnId: null,
  isRailExpanded: true,

  setTurns: (turns) => {
    set({ turns, activeTurnId: null, highlightedLineageChain: [] });
  },

  setFilterMode: (mode) => {
    set({ filterMode: mode });
  },

  selectTurn: (turnId) => {
    if (!turnId) {
      set({ activeTurnId: null, highlightedLineageChain: [] });
      return;
    }
    const chain = traceCausalityLineage(turnId, get().turns);
    set({ activeTurnId: turnId, highlightedLineageChain: chain });
  },

  setHoveredTurnId: (turnId) => {
    set({ hoveredTurnId: turnId });
  },

  toggleRailExpanded: () => {
    set((state) => ({ isRailExpanded: !state.isRailExpanded }));
  },

  resetStore: () => {
    set({
      turns: getDefaultTurns(),
      filterMode: 'all',
      activeTurnId: null,
      highlightedLineageChain: [],
      hoveredTurnId: null,
      isRailExpanded: true,
    });
  },
}));
