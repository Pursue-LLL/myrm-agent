import { create } from 'zustand';
import {
  OfficeWorkspaceMode,
  ModeSecurityPolicy,
  WriteIntentDetectionResult,
} from './threeModeTypes';
import {
  resolveModeSecurityPolicy,
  detectWriteIntentInAskMode,
} from './threeModeEngine';

interface ThreeModeState {
  currentMode: OfficeWorkspaceMode;
  policy: ModeSecurityPolicy;
  isMatrixOpen: boolean;
  intentGuidance: WriteIntentDetectionResult | null;
  modeSwitchHistory: Array<{
    from: OfficeWorkspaceMode;
    to: OfficeWorkspaceMode;
    timestamp: string;
  }>;

  setMode: (mode: OfficeWorkspaceMode) => void;
  checkUserInputIntent: (input: string) => WriteIntentDetectionResult;
  dismissIntentGuidance: () => void;
  toggleMatrix: () => void;
  closeMatrix: () => void;
}

export const useThreeModeStore = create<ThreeModeState>((set, get) => ({
  currentMode: 'ask',
  policy: resolveModeSecurityPolicy('ask'),
  isMatrixOpen: false,
  intentGuidance: null,
  modeSwitchHistory: [],

  setMode: (mode) => {
    const { currentMode, modeSwitchHistory } = get();
    if (currentMode === mode) {
      return;
    }

    const updatedHistory = [
      {
        from: currentMode,
        to: mode,
        timestamp: new Date().toLocaleTimeString(),
      },
      ...modeSwitchHistory,
    ].slice(0, 50);

    set({
      currentMode: mode,
      policy: resolveModeSecurityPolicy(mode),
      intentGuidance: null,
      modeSwitchHistory: updatedHistory,
    });
  },

  checkUserInputIntent: (input) => {
    const { currentMode } = get();
    const result = detectWriteIntentInAskMode(input, currentMode);
    if (result.hasWriteIntent) {
      set({ intentGuidance: result });
    } else {
      set({ intentGuidance: null });
    }
    return result;
  },

  dismissIntentGuidance: () => set({ intentGuidance: null }),

  toggleMatrix: () => set((state) => ({ isMatrixOpen: !state.isMatrixOpen })),

  closeMatrix: () => set({ isMatrixOpen: false }),
}));
