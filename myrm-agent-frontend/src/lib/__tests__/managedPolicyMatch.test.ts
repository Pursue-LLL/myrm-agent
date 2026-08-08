import { describe, expect, it } from 'vitest';
import {
  fnmatchCase,
  managedPolicyConstraintsForModel,
  mapSuppressesYoloForModel,
  matchesAnyModelPattern,
  orgBlocksYoloForModel,
} from '@/lib/managedPolicyMatch';

describe('fnmatchCase', () => {
  it('matches harness ignore_allowlist glob vectors', () => {
    expect(fnmatchCase('claude-opus*', 'claude-opus-4-20250514')).toBe(true);
    expect(fnmatchCase('claude-opus*', 'gpt-4o')).toBe(false);
    expect(fnmatchCase('gpt-*', 'gpt-4o')).toBe(true);
    expect(fnmatchCase('gpt-*', 'claude-opus-4')).toBe(false);
  });

  it('returns false for empty pattern or slug', () => {
    expect(fnmatchCase('', 'gpt-4o')).toBe(false);
    expect(fnmatchCase('gpt-*', '')).toBe(false);
  });
});

describe('managedPolicyConstraintsForModel', () => {
  const policy = {
    ignoreAllowlistForModels: ['claude-opus*'],
    forceAutoReviewForModels: ['gpt-*'],
  };

  it('applies force auto-review and ignore allowlist independently', () => {
    expect(managedPolicyConstraintsForModel(policy, 'claude-opus-4')).toEqual({
      forceAutoReview: false,
      ignoreAllowlist: true,
    });
    expect(managedPolicyConstraintsForModel(policy, 'gpt-4o')).toEqual({
      forceAutoReview: true,
      ignoreAllowlist: false,
    });
    expect(managedPolicyConstraintsForModel(policy, 'llama-3')).toEqual({
      forceAutoReview: false,
      ignoreAllowlist: false,
    });
  });
});

describe('mapSuppressesYoloForModel', () => {
  it('is true when force review or ignore allowlist matches', () => {
    const policy = { forceAutoReviewForModels: ['claude-opus*'] };
    expect(mapSuppressesYoloForModel(policy, 'claude-opus-4')).toBe(true);
    expect(mapSuppressesYoloForModel(policy, 'gpt-4o')).toBe(false);
  });
});

describe('orgBlocksYoloForModel', () => {
  it('blocks YOLO when org globally disables YOLO', () => {
    expect(
      orgBlocksYoloForModel({ disableYolo: true }, 'gpt-4o'),
    ).toBe(true);
  });

  it('blocks YOLO for per-model suppress rules', () => {
    expect(
      orgBlocksYoloForModel({ ignoreAllowlistForModels: ['gpt-*'] }, 'gpt-4o'),
    ).toBe(true);
  });
});

describe('matchesAnyModelPattern', () => {
  it('returns false when patterns empty or slug blank', () => {
    expect(matchesAnyModelPattern([], 'gpt-4o')).toBe(false);
    expect(matchesAnyModelPattern(['gpt-*'], '   ')).toBe(false);
  });
});
