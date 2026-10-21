export type SpotlightBadgeType =
  | 'flagship'
  | 'discount'
  | 'reasoning'
  | 'open-weights'
  | 'multimodal'
  | 'ultra-fast';

export interface BenchmarkMetric {
  label: string;
  score: string;
  vsPrior: string;
}

export interface SpotlightModelItem {
  id: string;
  modelId: string;
  name: string;
  provider: string;
  tagline: string;
  highlightBadges: SpotlightBadgeType[];
  contextWindow: number;
  pricingInputPerM: number;
  pricingOutputPerM: number;
  discountPercent?: number;
  releaseDate: string;
  spotlightGradient: {
    from: string;
    to: string;
    accent: string;
  };
  benchmarks: BenchmarkMetric[];
  samplePrompts: string[];
}

export interface PlaygroundMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
  latencyMs?: number;
}

export interface MountComparison {
  currentModelId: string;
  targetModelId: string;
  currentContextWindow: number;
  targetContextWindow: number;
  contextDeltaTokens: number;
  priceDeltaPercent: number;
  supportsVision: boolean;
  supportsReasoning: boolean;
}

export interface DismissRecord {
  spotlightId: string;
  dismissedAt: number;
  permanent: boolean;
}
