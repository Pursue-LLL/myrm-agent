import { describe, it, expect } from 'vitest';
import type {
  ModelPacingTier,
  ModelPacingSpec,
  PacingSuggestion,
  ModelPacingStoreState,
} from '../modelPacingTypes';

describe('modelPacingTypes', () => {
  it('correctly models ModelPacingSpec contract', () => {
    const spec: ModelPacingSpec = {
      tier: 'fast',
      displayName: '极速日常',
      subtitle: '低时延即时交付',
      description: '极速响应模式',
      recommendedUseCases: ['速记', '代码改错'],
      typicalLatencySec: '< 5s',
      badgeColor: 'sky',
      temperatureHint: 0.3,
      thinkingBudgetTokens: 0,
    };

    expect(spec.tier).toBe<ModelPacingTier>('fast');
    expect(spec.typicalLatencySec).toBe('< 5s');
    expect(spec.badgeColor).toBe('sky');
    expect(spec.temperatureHint).toBe(0.3);
  });

  it('correctly models PacingSuggestion contract', () => {
    const suggestion: PacingSuggestion = {
      suggestedTier: 'smart',
      matchedKeyword: '架构设计',
      reason: '需要复杂深度推导',
    };

    expect(suggestion.suggestedTier).toBe('smart');
    expect(suggestion.matchedKeyword).toBe('架构设计');
  });

  it('correctly models ModelPacingStoreState contract', () => {
    const state: ModelPacingStoreState = {
      activeTier: 'balanced',
      isPopoverOpen: false,
      perChatOverrides: {
        chat_101: 'smart',
      },
    };

    expect(state.activeTier).toBe('balanced');
    expect(state.perChatOverrides['chat_101']).toBe('smart');
  });
});
