/**
 * DefaultModelSection context window mismatch warning logic tests.
 *
 * Validates the condition: liteModel.max_input_tokens < baseModel.max_input_tokens
 */

import { describe, it, expect } from 'vitest';

interface SingleModelSelection {
  providerId: string;
  model: string;
}

interface CustomModelInfo {
  max_input_tokens?: number;
}

function shouldShowContextWindowWarning(
  basePrimary: SingleModelSelection | null,
  litePrimary: SingleModelSelection | null,
  customModelInfo: Record<string, CustomModelInfo>,
): boolean {
  if (!basePrimary || !litePrimary) return false;
  const baseWindow = customModelInfo[`${basePrimary.providerId}/${basePrimary.model}`]?.max_input_tokens;
  const liteWindow = customModelInfo[`${litePrimary.providerId}/${litePrimary.model}`]?.max_input_tokens;
  if (!baseWindow || !liteWindow || liteWindow >= baseWindow) return false;
  return true;
}

describe('DefaultModelSection context window mismatch warning', () => {
  const baseModel: SingleModelSelection = { providerId: 'anthropic', model: 'claude-opus-4' };
  const liteModel32K: SingleModelSelection = { providerId: 'openai', model: 'gpt-4o-mini' };
  const liteModel200K: SingleModelSelection = { providerId: 'google', model: 'gemini-2.5-flash' };

  const customModelInfo: Record<string, CustomModelInfo> = {
    'anthropic/claude-opus-4': { max_input_tokens: 200000 },
    'openai/gpt-4o-mini': { max_input_tokens: 32000 },
    'google/gemini-2.5-flash': { max_input_tokens: 1000000 },
  };

  it('shows warning when lite model window < base model window', () => {
    expect(shouldShowContextWindowWarning(baseModel, liteModel32K, customModelInfo)).toBe(true);
  });

  it('hides warning when lite model window >= base model window', () => {
    expect(shouldShowContextWindowWarning(baseModel, liteModel200K, customModelInfo)).toBe(false);
  });

  it('hides warning when base model is null', () => {
    expect(shouldShowContextWindowWarning(null, liteModel32K, customModelInfo)).toBe(false);
  });

  it('hides warning when lite model is null', () => {
    expect(shouldShowContextWindowWarning(baseModel, null, customModelInfo)).toBe(false);
  });

  it('hides warning when base model has no max_input_tokens data', () => {
    const infoWithoutBase: Record<string, CustomModelInfo> = {
      'openai/gpt-4o-mini': { max_input_tokens: 32000 },
    };
    expect(shouldShowContextWindowWarning(baseModel, liteModel32K, infoWithoutBase)).toBe(false);
  });

  it('hides warning when lite model has no max_input_tokens data', () => {
    const infoWithoutLite: Record<string, CustomModelInfo> = {
      'anthropic/claude-opus-4': { max_input_tokens: 200000 },
    };
    expect(shouldShowContextWindowWarning(baseModel, liteModel32K, infoWithoutLite)).toBe(false);
  });

  it('hides warning when both models have equal window size', () => {
    const equalInfo: Record<string, CustomModelInfo> = {
      'anthropic/claude-opus-4': { max_input_tokens: 128000 },
      'openai/gpt-4o-mini': { max_input_tokens: 128000 },
    };
    expect(shouldShowContextWindowWarning(baseModel, liteModel32K, equalInfo)).toBe(false);
  });

  it('hides warning when customModelInfo is empty', () => {
    expect(shouldShowContextWindowWarning(baseModel, liteModel32K, {})).toBe(false);
  });
});
