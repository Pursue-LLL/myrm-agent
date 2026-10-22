import { create } from 'zustand';
import {
  PrebakedThemeBaseline,
  ThemeInvariantSuiteReport,
  ThemeLayerInvariantState,
  ThemeMode,
} from './themeLayerInvariantTypes';
import {
  compareWithPrebakedBaseline,
  evaluateThemeInvariantSuite,
} from './themeLayerInvariantEngine';

export interface ThemeLayerInvariantActions {
  evaluateCurrentTheme: (
    lightCanvasHex: string,
    lightCardHex: string,
    darkCanvasHex: string,
    darkCardHex: string
  ) => ThemeInvariantSuiteReport;
  selectBaseline: (baseline: PrebakedThemeBaseline | null) => void;
  toggleBaselineModal: (open?: boolean) => void;
  applyQuickThemeFix: (mode: ThemeMode) => void;
  reset: () => void;
}

export type ThemeLayerInvariantStore = ThemeLayerInvariantState &
  ThemeLayerInvariantActions & {
    prebakedBaselines: PrebakedThemeBaseline[];
  };

const defaultPrebakedBaselines: PrebakedThemeBaseline[] = [
  {
    baselineVersion: 'v0.9.0-clean',
    capturedAt: 1726000000000,
    lightMode: {
      canvasHex: '#ffffff',
      cardHex: '#ffffff',
      isCorrect: true,
    },
    darkMode: {
      canvasHex: '#09090b',
      cardHex: '#18181b',
      isCorrect: true,
    },
  },
  {
    baselineVersion: 'v0.10.0-recessed-buggy',
    capturedAt: 1726300000000,
    lightMode: {
      canvasHex: '#ffffff',
      cardHex: '#e7e7e8', // 错误调暗 24 级导致凹陷/发灰
      isCorrect: false,
    },
    darkMode: {
      canvasHex: '#09090b',
      cardHex: '#18181b',
      isCorrect: true,
    },
  },
];

const initialState: ThemeLayerInvariantState = {
  currentReport: null,
  selectedBaseline: defaultPrebakedBaselines[0],
  isBaselineModalOpen: false,
};

export const useThemeLayerInvariantStore = create<ThemeLayerInvariantStore>(
  (set, get) => ({
    ...initialState,
    prebakedBaselines: defaultPrebakedBaselines,

    evaluateCurrentTheme: (
      lightCanvasHex,
      lightCardHex,
      darkCanvasHex,
      darkCardHex
    ) => {
      const report = evaluateThemeInvariantSuite(
        lightCanvasHex,
        lightCardHex,
        darkCanvasHex,
        darkCardHex
      );

      const { selectedBaseline } = get();
      if (selectedBaseline) {
        const comparison = compareWithPrebakedBaseline(
          report,
          selectedBaseline
        );
        report.baselineComparison = comparison;
      }

      set({ currentReport: report });
      return report;
    },

    selectBaseline: (baseline) => {
      set({ selectedBaseline: baseline });
      const { currentReport } = get();
      if (currentReport && baseline) {
        const comparison = compareWithPrebakedBaseline(currentReport, baseline);
        set({
          currentReport: {
            ...currentReport,
            baselineComparison: comparison,
          },
        });
      }
    },

    toggleBaselineModal: (open) => {
      set((state) => ({
        isBaselineModalOpen:
          typeof open === 'boolean' ? open : !state.isBaselineModalOpen,
      }));
    },

    applyQuickThemeFix: (mode: ThemeMode) => {
      const { currentReport } = get();
      if (!currentReport) {
        return;
      }

      if (mode === 'light') {
        // 浅色修正：将卡片明度调整为与画布一致（#ffffff），抬升由描边与阴影承担
        get().evaluateCurrentTheme(
          currentReport.lightEvaluation.canvasHex,
          '#ffffff',
          currentReport.darkEvaluation.canvasHex,
          currentReport.darkEvaluation.cardHex
        );
      } else {
        // 深色修正：将卡片明度调整为高于底色（例如底色 #09090b，卡面 #18181b）
        get().evaluateCurrentTheme(
          currentReport.lightEvaluation.canvasHex,
          currentReport.lightEvaluation.cardHex,
          currentReport.darkEvaluation.canvasHex,
          '#18181b'
        );
      }
    },

    reset: () => {
      set({
        ...initialState,
        prebakedBaselines: defaultPrebakedBaselines,
      });
    },
  })
);
