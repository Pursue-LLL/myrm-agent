/**
 * [INPUT]
 * - None (Pure domain type definitions for Tri-Tier Model Execution Pacing Selector)
 *
 * [OUTPUT]
 * - ModelPacingTier, ModelPacingSpec, PacingSuggestion, ModelPacingStoreState
 *
 * [POS]
 * Unified contract for Item 191: TriTierModelExecutionPacingSelectorAndP1LatencyPresetSuite.
 * Abstracting complex model matrices into three intuitive execution speeds:
 * Fast (Daily P1 low-latency) / Balanced (Everyday dev) / Smart (Deep reasoning & audit).
 */

export type ModelPacingTier = 'fast' | 'balanced' | 'smart';

export interface ModelPacingSpec {
  readonly tier: ModelPacingTier;
  readonly displayName: string;
  readonly subtitle: string;
  readonly description: string;
  readonly recommendedUseCases: readonly string[];
  readonly typicalLatencySec: string;
  readonly badgeColor: 'sky' | 'emerald' | 'purple';
  readonly temperatureHint: number;
  readonly thinkingBudgetTokens?: number;
}

export interface PacingSuggestion {
  readonly suggestedTier: ModelPacingTier;
  readonly matchedKeyword: string;
  readonly reason: string;
}

export interface ModelPacingStoreState {
  readonly activeTier: ModelPacingTier;
  readonly isPopoverOpen: boolean;
  readonly perChatOverrides: Readonly<Record<string, ModelPacingTier>>;
}
