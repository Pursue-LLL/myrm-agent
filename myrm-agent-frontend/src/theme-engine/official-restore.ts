import type { ThemeProfileRecipe } from './schema';
import { OFFICIAL_DEFAULT_PROFILE_ID } from './presets';
import { EMPTY_THEME_PROFILES, hasArtOverlay } from './overlay';

export interface ThemeRestoreState {
  activeThemeProfileId: string | null | undefined;
  themeProfiles: ThemeProfileRecipe[];
  themeFontOverride: string | null | undefined;
}

export interface OfficialThemeRestorePatch {
  activeThemeProfileId: string;
  themeProfiles: ThemeProfileRecipe[];
  themeFontOverride: undefined;
}

function hasManagedCustomProfiles(profiles: ThemeProfileRecipe[]): boolean {
  return profiles.some((profile) => profile.id.startsWith('studio/') || profile.id.startsWith('imported/'));
}

export function buildOfficialThemeRestorePatch(): OfficialThemeRestorePatch {
  return {
    activeThemeProfileId: OFFICIAL_DEFAULT_PROFILE_ID,
    themeProfiles: EMPTY_THEME_PROFILES,
    themeFontOverride: undefined,
  };
}

export function isThemeDeviatedFromOfficial(state: ThemeRestoreState): boolean {
  const activeId = state.activeThemeProfileId ?? OFFICIAL_DEFAULT_PROFILE_ID;
  if (activeId !== OFFICIAL_DEFAULT_PROFILE_ID) {
    return true;
  }
  if (hasArtOverlay(state.themeProfiles)) {
    return true;
  }
  if (hasManagedCustomProfiles(state.themeProfiles)) {
    return true;
  }
  if (state.themeFontOverride != null && state.themeFontOverride !== '') {
    return true;
  }
  return false;
}

export function needsRestoreConfirm(state: ThemeRestoreState): boolean {
  return hasArtOverlay(state.themeProfiles) || hasManagedCustomProfiles(state.themeProfiles);
}
