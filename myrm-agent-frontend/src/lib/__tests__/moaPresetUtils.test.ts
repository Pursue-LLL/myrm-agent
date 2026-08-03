import { describe, expect, it } from 'vitest';
import {
  MOA_PRESET_DEFAULT_ID,
  MOA_PRESET_FAST_ID,
  MOA_PRESET_REVIEW_ID,
  countMoaReferenceModels,
  isMoaPresetConfigured,
  listMoaPresetOptions,
} from '@/lib/moaPresetUtils';

describe('moaPresetUtils', () => {
  it('detects configured preset when enabled with reference models', () => {
    const engineParams = {
      moa_overlay: {
        enabled: true,
        reference_model_selections: [{ providerId: 'openai', model: 'gpt-4o-mini' }],
      },
    };
    expect(isMoaPresetConfigured(engineParams)).toBe(true);
    expect(countMoaReferenceModels(engineParams)).toBe(1);
  });

  it('returns false when overlay disabled or missing refs', () => {
    expect(
      isMoaPresetConfigured({
        moa_overlay: { enabled: false, reference_model_selections: [{ providerId: 'x', model: 'y' }] },
      }),
    ).toBe(false);
    expect(isMoaPresetConfigured({ moa_overlay: { enabled: true } })).toBe(false);
    expect(isMoaPresetConfigured(null)).toBe(false);
  });

  it('lists default, review, and fast preset options', () => {
    const engineParams = {
      moa_overlay: {
        enabled: true,
        reference_model_selections: [
          { providerId: 'openai', model: 'gpt-4o-mini' },
          { providerId: 'openai', model: 'gpt-4o' },
        ],
      },
    };
    const options = listMoaPresetOptions(engineParams);
    expect(options.map((option) => option.id)).toEqual([
      MOA_PRESET_DEFAULT_ID,
      MOA_PRESET_REVIEW_ID,
      MOA_PRESET_FAST_ID,
    ]);
    expect(options.every((option) => option.refCount === 2)).toBe(true);
  });
});
