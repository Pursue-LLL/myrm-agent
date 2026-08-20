import { describe, expect, it } from 'vitest';

import { buildOfficialThemeRestorePatch, isThemeDeviatedFromOfficial, needsRestoreConfirm } from '../official-restore';
import { OFFICIAL_DEFAULT_PROFILE_ID, getDefaultThemeProfile } from '../presets';
import { buildArtOverlayProfile, EMPTY_THEME_PROFILES } from '../overlay';

describe('official-restore', () => {
  it('buildOfficialThemeRestorePatch resets to official default', () => {
    expect(buildOfficialThemeRestorePatch()).toEqual({
      activeThemeProfileId: OFFICIAL_DEFAULT_PROFILE_ID,
      themeProfiles: EMPTY_THEME_PROFILES,
      themeFontOverride: undefined,
    });
  });

  it('isThemeDeviatedFromOfficial is false at official default with no custom state', () => {
    expect(
      isThemeDeviatedFromOfficial({
        activeThemeProfileId: OFFICIAL_DEFAULT_PROFILE_ID,
        themeProfiles: [],
        themeFontOverride: undefined,
      }),
    ).toBe(false);
  });

  it('isThemeDeviatedFromOfficial is true for non-official builtin preset', () => {
    expect(
      isThemeDeviatedFromOfficial({
        activeThemeProfileId: 'preset-rose',
        themeProfiles: [],
        themeFontOverride: undefined,
      }),
    ).toBe(true);
  });

  it('isThemeDeviatedFromOfficial is true when art overlay exists', () => {
    const base = getDefaultThemeProfile();
    const overlay = buildArtOverlayProfile(base, 'file:hero', 'image');
    expect(
      isThemeDeviatedFromOfficial({
        activeThemeProfileId: OFFICIAL_DEFAULT_PROFILE_ID,
        themeProfiles: [overlay],
        themeFontOverride: undefined,
      }),
    ).toBe(true);
  });

  it('needsRestoreConfirm is true for studio profiles but false for preset-only deviation', () => {
    expect(
      needsRestoreConfirm({
        activeThemeProfileId: 'preset-rose',
        themeProfiles: [],
        themeFontOverride: undefined,
      }),
    ).toBe(false);

    expect(
      needsRestoreConfirm({
        activeThemeProfileId: OFFICIAL_DEFAULT_PROFILE_ID,
        themeProfiles: [{ ...getDefaultThemeProfile(), id: 'studio/abc', builtin: false }],
        themeFontOverride: undefined,
      }),
    ).toBe(true);
  });
});
