export type ThemeMode = 'light' | 'dark';

export interface LayerDirectionEvaluation {
  mode: ThemeMode;
  canvasHex: string;
  cardHex: string;
  canvasLightness: number;
  cardLightness: number;
  deltaLightness: number;
  isInvariantSatisfied: boolean;
  violationReason?: string;
}

export interface PrebakedThemeBaseline {
  baselineVersion: string;
  capturedAt: number;
  lightMode: {
    canvasHex: string;
    cardHex: string;
    isCorrect: boolean;
  };
  darkMode: {
    canvasHex: string;
    cardHex: string;
    isCorrect: boolean;
  };
}

export interface ThemeInvariantSuiteReport {
  timestamp: number;
  lightEvaluation: LayerDirectionEvaluation;
  darkEvaluation: LayerDirectionEvaluation;
  allPassed: boolean;
  baselineComparison?: {
    hasRegression: boolean;
    details: string[];
  };
}

export interface ThemeLayerInvariantState {
  currentReport: ThemeInvariantSuiteReport | null;
  selectedBaseline: PrebakedThemeBaseline | null;
  isBaselineModalOpen: boolean;
}
