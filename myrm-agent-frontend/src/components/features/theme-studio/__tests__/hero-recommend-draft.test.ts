import { describe, expect, it } from 'vitest';
import {
  buildHeroSampleApplyPatch,
  shouldClearHeroSampleOnDraftPatch,
} from '../hero-recommend-draft';
import type { HeroImageSample } from '@/theme-engine';

const SAMPLE: HeroImageSample = {
  primaryHex: '#2563eb',
  focalX: 0.72,
  focalY: 0.28,
  aspectRatio: 1.6,
  recommendedLayoutId: 'full-bleed',
};

describe('shouldClearHeroSampleOnDraftPatch', () => {
  it('clears when layoutId is patched manually', () => {
    expect(shouldClearHeroSampleOnDraftPatch({ layoutId: 'work-dense' })).toBe(true);
  });

  it('clears when palette is patched manually', () => {
    expect(
      shouldClearHeroSampleOnDraftPatch({
        palette: {
          primaryLight: '#111111',
          primaryDark: '#eeeeee',
          primaryHoverLight: '#222222',
          primaryHoverDark: '#dddddd',
          primaryDarkLight: '#333333',
          primaryDarkDark: '#cccccc',
          dualAccent: false,
        },
      }),
    ).toBe(true);
  });

  it('does not clear for art-only focal tweaks', () => {
    expect(
      shouldClearHeroSampleOnDraftPatch({
        art: {
          mediaKind: 'image',
          assetRef: 'file:abc',
          posterAssetRef: null,
          focusX: 0.5,
          focusY: 0.5,
          wash: 0.35,
        },
      }),
    ).toBe(false);
  });
});

describe('buildHeroSampleApplyPatch', () => {
  it('returns palette and layout only (no focal — focal applied on upload)', () => {
    const patch = buildHeroSampleApplyPatch(SAMPLE);
    expect(patch.layoutId).toBe('full-bleed');
    expect(patch.palette.primaryLight).toMatch(/^#[0-9a-f]{6}$/i);
    expect(patch).not.toHaveProperty('art');
    expect(Object.keys(patch).sort()).toEqual(['layoutId', 'palette']);
  });

  it('does not embed stale focal values that would revert manual slider edits', () => {
    const patch = buildHeroSampleApplyPatch(SAMPLE);
    expect(JSON.stringify(patch)).not.toContain('focal');
    expect(JSON.stringify(patch)).not.toContain('0.72');
  });
});
