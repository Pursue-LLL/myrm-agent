import { describe, it, expect } from 'vitest';
import {
  resolvePacingSpec,
  mapOptimizationModeToPacingTier,
  mapPacingTierToOptimizationMode,
  suggestPacingTierForPrompt,
} from '../modelPacingEngine';

describe('modelPacingEngine', () => {
  describe('resolvePacingSpec', () => {
    it('resolves fast tier spec correctly', () => {
      const spec = resolvePacingSpec('fast');
      expect(spec.tier).toBe('fast');
      expect(spec.displayName).toBe('极速日常');
      expect(spec.typicalLatencySec).toBe('< 5s');
      expect(spec.thinkingBudgetTokens).toBe(0);
      expect(spec.badgeColor).toBe('sky');
    });

    it('resolves balanced tier spec correctly', () => {
      const spec = resolvePacingSpec('balanced');
      expect(spec.tier).toBe('balanced');
      expect(spec.displayName).toBe('平衡推荐');
      expect(spec.typicalLatencySec).toBe('10-25s');
      expect(spec.thinkingBudgetTokens).toBe(2048);
      expect(spec.badgeColor).toBe('emerald');
    });

    it('resolves smart tier spec correctly', () => {
      const spec = resolvePacingSpec('smart');
      expect(spec.tier).toBe('smart');
      expect(spec.displayName).toBe('深度推理');
      expect(spec.typicalLatencySec).toBe('30-90s');
      expect(spec.thinkingBudgetTokens).toBe(8192);
      expect(spec.badgeColor).toBe('purple');
    });
  });

  describe('mode mapping', () => {
    it('maps optimization modes to pacing tiers', () => {
      expect(mapOptimizationModeToPacingTier('speed')).toBe('fast');
      expect(mapOptimizationModeToPacingTier('quality')).toBe('smart');
      expect(mapOptimizationModeToPacingTier('deep')).toBe('smart');
      expect(mapOptimizationModeToPacingTier('balanced')).toBe('balanced');
      expect(mapOptimizationModeToPacingTier(undefined)).toBe('balanced');
      expect(mapOptimizationModeToPacingTier(null)).toBe('balanced');
    });

    it('maps pacing tiers back to optimization modes', () => {
      expect(mapPacingTierToOptimizationMode('fast')).toBe('speed');
      expect(mapPacingTierToOptimizationMode('smart')).toBe('quality');
      expect(mapPacingTierToOptimizationMode('balanced')).toBe('balanced');
    });
  });

  describe('suggestPacingTierForPrompt', () => {
    it('returns null for empty or conversational text', () => {
      expect(suggestPacingTierForPrompt('')).toBeNull();
      expect(suggestPacingTierForPrompt('   ')).toBeNull();
      expect(suggestPacingTierForPrompt('你好，请问今天星期几？')).toBeNull();
    });

    it('suggests smart tier for complex architecture or deep reasoning prompts', () => {
      const suggestion = suggestPacingTierForPrompt('请给出微服务高可用架构设计的详细方案');
      expect(suggestion).not.toBeNull();
      expect(suggestion?.suggestedTier).toBe('smart');
      expect(suggestion?.matchedKeyword).toBe('架构设计');
    });

    it('suggests fast tier for typo fixing or translation', () => {
      const suggestion = suggestPacingTierForPrompt('帮我改错字，并快速总结这段要点');
      expect(suggestion).not.toBeNull();
      expect(suggestion?.suggestedTier).toBe('fast');
      expect(suggestion?.matchedKeyword).toMatch(/改错字|快速总结/);
    });
  });
});
