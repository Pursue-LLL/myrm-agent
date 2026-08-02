import { describe, expect, it } from 'vitest';
import {
  USER_ART_OVERLAY_ID,
  ART_WASH_MAX,
  ART_WASH_MIN,
  buildArtOverlayProfile,
  getArtOverlayProfile,
  hasArtOverlay,
  mediaKindFromFile,
  mergeArtOverlay,
  stripArtOverlay,
  updateArtOverlayWash,
  upsertArtOverlayProfile,
  validateThemeBackgroundFile,
} from '../overlay';
import { getDefaultThemeProfile } from '../presets';

describe('theme-engine overlay', () => {
  it('merges art overlay onto active profile', () => {
    const base = getDefaultThemeProfile();
    const overlay = buildArtOverlayProfile(base, 'file:abc', 'image');
    const merged = mergeArtOverlay(base, [overlay]);
    expect(merged.art.assetRef).toBe('file:abc');
    expect(merged.art.mediaKind).toBe('image');
    expect(merged.id).toBe(base.id);
  });

  it('upserts and strips overlay profiles', () => {
    const base = getDefaultThemeProfile();
    const overlay = buildArtOverlayProfile(base, 'file:xyz', 'video', 'file:poster');
    const withOverlay = upsertArtOverlayProfile([], overlay);
    expect(withOverlay).toHaveLength(1);
    expect(withOverlay[0]?.id).toBe(USER_ART_OVERLAY_ID);
    expect(withOverlay[0]?.art.posterAssetRef).toBe('file:poster');
    expect(hasArtOverlay(withOverlay)).toBe(true);
    expect(stripArtOverlay(withOverlay)).toHaveLength(0);
  });

  it('rejects invalid and oversized background files', () => {
    expect(validateThemeBackgroundFile(new File([], 'empty.png', { type: 'image/png' }))).toBe('empty');
    expect(validateThemeBackgroundFile(new File(['x'], 'bad.txt', { type: 'text/plain' }))).toBe('invalidType');
    const big = new File([new Uint8Array(81 * 1024 * 1024)], 'big.png', { type: 'image/png' });
    expect(validateThemeBackgroundFile(big)).toBe('tooLarge');
  });

  it('updates overlay wash within bounds', () => {
    const base = getDefaultThemeProfile();
    const overlay = buildArtOverlayProfile(base, 'file:abc', 'image');
    const withOverlay = upsertArtOverlayProfile([], overlay);
    const updated = updateArtOverlayWash(withOverlay, 0.95);
    const next = getArtOverlayProfile(updated);
    expect(next?.art.wash).toBe(ART_WASH_MAX);
    const lowered = updateArtOverlayWash(updated, 0.1);
    expect(getArtOverlayProfile(lowered)?.art.wash).toBe(ART_WASH_MIN);
  });

  it('detects mp4 by extension when mime type is empty', () => {
    const file = new File(['x'], 'loop.mp4', { type: '' });
    expect(mediaKindFromFile(file)).toBe('video');
  });
});
