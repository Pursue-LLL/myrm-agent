import { beforeEach, describe, expect, it, vi } from 'vitest';

import { OFFICIAL_DEFAULT_PROFILE_ID, EMPTY_THEME_PROFILES } from '@/theme-engine';

const updatePersonalSettings = vi.fn().mockResolvedValue(undefined);
const resetDraft = vi.fn();
const clearPreview = vi.fn();

vi.mock('@/store/useConfigStore', () => ({
  default: {
    getState: () => ({
      updatePersonalSettings,
      personalSettings: {},
    }),
  },
}));

vi.mock('@/store/useThemeStudioDraftStore', () => ({
  default: {
    getState: () => ({ resetDraft }),
  },
}));

vi.mock('@/store/useThemeStudioDomPreviewStore', () => ({
  default: {
    getState: () => ({ clearPreview }),
  },
}));

describe('executeOfficialThemeRestore', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('writes official patch and clears studio side effects', async () => {
    const { executeOfficialThemeRestore } = await import('../restoreOfficialTheme');

    await executeOfficialThemeRestore();

    expect(updatePersonalSettings).toHaveBeenCalledWith({
      activeThemeProfileId: OFFICIAL_DEFAULT_PROFILE_ID,
      themeProfiles: EMPTY_THEME_PROFILES,
      themeFontOverride: undefined,
    });
    expect(resetDraft).toHaveBeenCalledOnce();
    expect(clearPreview).toHaveBeenCalledOnce();
  });
});
