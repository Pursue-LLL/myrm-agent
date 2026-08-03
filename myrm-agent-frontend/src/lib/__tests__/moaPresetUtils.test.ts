import { describe, expect, it } from 'vitest';
import {
  buildPresetsForMoaEnable,
  countMoaReferenceModelsForPreset,
  emptyMoaPresetsMap,
  isActiveMoaPresetAvailable,
  isMoaPresetConfigured,
  listMoaPresetOptions,
  MOA_PRESET_FAST_ID,
  MOA_PRESET_REVIEW_ID,
  resolvePresetReferenceSelections,
} from '@/lib/moaPresetUtils';

describe('moaPresetUtils per-preset refs', () => {
  const engineParams = {
    moa_overlay: {
      enabled: true,
      reference_model_selections: [{ providerId: 'openai', model: 'gpt-4o-mini' }],
      presets: {
        review: {
          reference_model_selections: [{ providerId: 'anthropic', model: 'claude-3-5-sonnet' }],
        },
        fast: {
          reference_model_selections: [{ providerId: 'openai', model: 'gpt-4o-mini' }],
        },
      },
    },
  };

  it('resolves preset-specific refs before top-level fallback', () => {
    const overlay = engineParams.moa_overlay as Record<string, unknown>;
    const reviewRefs = resolvePresetReferenceSelections(overlay, MOA_PRESET_REVIEW_ID);
    expect(reviewRefs[0]?.model).toBe('claude-3-5-sonnet');
  });

  it('returns empty refs when preset block is explicitly empty', () => {
    const overlay = {
      enabled: true,
      reference_model_selections: [{ providerId: 'openai', model: 'gpt-4o-mini' }],
      presets: {
        default: { reference_model_selections: [] },
        fast: { reference_model_selections: [] },
      },
    };
    expect(resolvePresetReferenceSelections(overlay, MOA_PRESET_FAST_ID)).toEqual([]);
  });

  it('falls back to top-level refs for legacy profiles without presets key', () => {
    const overlay = {
      enabled: true,
      reference_model_selections: [{ providerId: 'openai', model: 'gpt-4o-mini' }],
    };
    const refs = resolvePresetReferenceSelections(overlay, MOA_PRESET_REVIEW_ID);
    expect(refs[0]?.model).toBe('gpt-4o-mini');
  });

  it('lists only presets with refCount > 0', () => {
    const options = listMoaPresetOptions(engineParams);
    // default has no presets.default block — strict mode ignores top-level fallback
    expect(options.map((o) => o.id)).toEqual(['review', 'fast']);
    expect(countMoaReferenceModelsForPreset(engineParams, MOA_PRESET_FAST_ID)).toBe(1);
  });

  it('detects configured overlay from preset-only refs', () => {
    const params = {
      moa_overlay: {
        enabled: true,
        presets: {
          fast: {
            reference_model_selections: [{ providerId: 'openai', model: 'gpt-4o-mini' }],
          },
        },
      },
    };
    expect(isMoaPresetConfigured(params)).toBe(true);
  });

  it('isActiveMoaPresetAvailable rejects stale preset ids', () => {
    const params = {
      moa_overlay: {
        enabled: true,
        reference_model_selections: [{ providerId: 'openai', model: 'gpt-4o-mini' }],
        presets: {
          review: {
            reference_model_selections: [{ providerId: 'anthropic', model: 'claude-3-5-sonnet' }],
          },
          fast: { reference_model_selections: [] },
        },
      },
    };
    expect(isActiveMoaPresetAvailable(params, 'review')).toBe(true);
    expect(isActiveMoaPresetAvailable(params, 'fast')).toBe(false);
  });

  it('buildPresetsForMoaEnable migrates top-level refs into presets.default', () => {
    const overlay = {
      reference_model_selections: [{ providerId: 'openai', model: 'gpt-4o-mini' }],
    };
    const presets = buildPresetsForMoaEnable(overlay);
    expect(presets.default.reference_model_selections[0]?.model).toBe('gpt-4o-mini');
    expect(presets.review.reference_model_selections).toEqual([]);
  });

  it('isMoaPresetConfigured ignores top-level refs when presets key exists', () => {
    const params = {
      moa_overlay: {
        enabled: true,
        reference_model_selections: [{ providerId: 'openai', model: 'gpt-4o-mini' }],
        presets: emptyMoaPresetsMap(),
      },
    };
    expect(isMoaPresetConfigured(params)).toBe(false);
  });
});
