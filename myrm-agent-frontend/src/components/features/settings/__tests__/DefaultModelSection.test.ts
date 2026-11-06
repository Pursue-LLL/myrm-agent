/**
 * Context window mismatch warning of the quick model card.
 *
 * Validates the condition: liteModel.max_input_tokens < baseModel.max_input_tokens
 */

import { describe, it, expect } from 'vitest';

import type { CustomModelInfo, SingleModelSelection } from '@/store/config/providerTypes';
import { isLiteWindowBelowBase } from '../default-model/LiteModelCard';

type ModelWindows = Record<string, Pick<CustomModelInfo, 'max_input_tokens'>>;

describe('isLiteWindowBelowBase', () => {
  const baseModel: SingleModelSelection = { providerId: 'anthropic', model: 'claude-opus-4' };
  const liteModel32K: SingleModelSelection = { providerId: 'openai', model: 'gpt-4o-mini' };
  const liteModel200K: SingleModelSelection = { providerId: 'google', model: 'gemini-2.5-flash' };

  const customModelInfo: ModelWindows = {
    'anthropic/claude-opus-4': { max_input_tokens: 200000 },
    'openai/gpt-4o-mini': { max_input_tokens: 32000 },
    'google/gemini-2.5-flash': { max_input_tokens: 1000000 },
  };

  it('shows warning when lite model window < base model window', () => {
    expect(isLiteWindowBelowBase(baseModel, liteModel32K, customModelInfo)).toBe(true);
  });

  it('hides warning when lite model window >= base model window', () => {
    expect(isLiteWindowBelowBase(baseModel, liteModel200K, customModelInfo)).toBe(false);
  });

  it('hides warning when base model is null', () => {
    expect(isLiteWindowBelowBase(null, liteModel32K, customModelInfo)).toBe(false);
  });

  it('hides warning when lite model is null', () => {
    expect(isLiteWindowBelowBase(baseModel, null, customModelInfo)).toBe(false);
  });

  it('hides warning when base model has no max_input_tokens data', () => {
    const infoWithoutBase: ModelWindows = {
      'openai/gpt-4o-mini': { max_input_tokens: 32000 },
    };
    expect(isLiteWindowBelowBase(baseModel, liteModel32K, infoWithoutBase)).toBe(false);
  });

  it('hides warning when lite model has no max_input_tokens data', () => {
    const infoWithoutLite: ModelWindows = {
      'anthropic/claude-opus-4': { max_input_tokens: 200000 },
    };
    expect(isLiteWindowBelowBase(baseModel, liteModel32K, infoWithoutLite)).toBe(false);
  });

  it('hides warning when both models have equal window size', () => {
    const equalInfo: ModelWindows = {
      'anthropic/claude-opus-4': { max_input_tokens: 128000 },
      'openai/gpt-4o-mini': { max_input_tokens: 128000 },
    };
    expect(isLiteWindowBelowBase(baseModel, liteModel32K, equalInfo)).toBe(false);
  });

  it('hides warning when customModelInfo is empty', () => {
    expect(isLiteWindowBelowBase(baseModel, liteModel32K, {})).toBe(false);
  });
});
