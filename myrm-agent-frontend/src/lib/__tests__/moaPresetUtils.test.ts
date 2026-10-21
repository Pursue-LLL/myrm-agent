import { describe, expect, it } from 'vitest';
import {
  buildPresetsForMoaEnable,
  countMoaReferenceModelsForPreset,
  emptyMoaPresetsMap,
  isActiveMoaPresetAvailable,
  isMoaAutoActivatedForProfile,
  isMoaPresetConfigured,
  listMoaPresetOptions,
  MOA_PRESET_FAST_ID,
  MOA_PRESET_REVIEW_ID,
  resolveEffectiveMoaPresetId,
  resolvePresetReferenceSelections,
  resolveProfileDefaultMoaPresetId,
  resolveProfileMoaActivationMode,
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

describe('AgentProfileAdvisorAutoActivationPolicy frontend utilities', () => {
  const baseConfiguredParams = {
    moa_overlay: {
      enabled: true,
      activation_mode: 'manual',
      default_preset_id: 'review',
      presets: {
        review: {
          reference_model_selections: [{ providerId: 'anthropic', model: 'claude-3-5-sonnet' }],
        },
        fast: {
          reference_model_selections: [{ providerId: 'openai', model: 'gpt-4o-mini' }],
        },
        default: {
          reference_model_selections: [],
        },
      },
    },
  };

  it('resolves activation mode from profile correctly', () => {
    expect(resolveProfileMoaActivationMode(baseConfiguredParams)).toBe('manual');

    const alwaysParams = {
      moa_overlay: { ...baseConfiguredParams.moa_overlay, activation_mode: 'always' },
    };
    expect(resolveProfileMoaActivationMode(alwaysParams)).toBe('always');

    const riskParams = {
      moa_overlay: { ...baseConfiguredParams.moa_overlay, activation_mode: 'risk_triggered' },
    };
    expect(resolveProfileMoaActivationMode(riskParams)).toBe('risk_triggered');

    const legacyAutoReasoning = {
      moa_overlay: { ...baseConfiguredParams.moa_overlay, activation_mode: undefined, auto_on_reasoning: true },
    };
    expect(resolveProfileMoaActivationMode(legacyAutoReasoning)).toBe('risk_triggered');
  });

  it('resolves default preset id with fallback to review', () => {
    expect(resolveProfileDefaultMoaPresetId(baseConfiguredParams)).toBe('review');

    const fastDefault = {
      moa_overlay: { ...baseConfiguredParams.moa_overlay, default_preset_id: 'fast' },
    };
    expect(resolveProfileDefaultMoaPresetId(fastDefault)).toBe('fast');
  });

  it('evaluates isMoaAutoActivatedForProfile accurately', () => {
    const alwaysParams = {
      moa_overlay: { ...baseConfiguredParams.moa_overlay, activation_mode: 'always' },
    };
    expect(isMoaAutoActivatedForProfile(alwaysParams)).toBe(true);

    const riskParams = {
      moa_overlay: { ...baseConfiguredParams.moa_overlay, activation_mode: 'risk_triggered' },
    };
    // No risk signals -> false
    expect(isMoaAutoActivatedForProfile(riskParams)).toBe(false);
    // Reasoning tier -> true
    expect(isMoaAutoActivatedForProfile(riskParams, 'reasoning')).toBe(true);
    // Risk trigger flag -> true
    expect(isMoaAutoActivatedForProfile(riskParams, 'chat', true)).toBe(true);
  });

  it('resolveEffectiveMoaPresetId prioritizes user request and falls back to auto policy', () => {
    const alwaysParams = {
      moa_overlay: { ...baseConfiguredParams.moa_overlay, activation_mode: 'always' },
    };

    // User explicitly requested fast
    expect(resolveEffectiveMoaPresetId(alwaysParams, 'fast')).toBe('fast');

    // User explicitly disabled
    expect(resolveEffectiveMoaPresetId(alwaysParams, 'none')).toBe(null);
    expect(resolveEffectiveMoaPresetId(alwaysParams, 'disabled')).toBe(null);

    // No user request -> auto activates review
    expect(resolveEffectiveMoaPresetId(alwaysParams)).toBe('review');

    // Risk triggered params
    const riskParams = {
      moa_overlay: { ...baseConfiguredParams.moa_overlay, activation_mode: 'risk_triggered' },
    };
    expect(resolveEffectiveMoaPresetId(riskParams)).toBe(null);
    expect(resolveEffectiveMoaPresetId(riskParams, null, 'reasoning')).toBe('review');
  });
});

