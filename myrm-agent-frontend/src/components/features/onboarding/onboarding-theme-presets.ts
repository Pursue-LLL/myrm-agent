import {
  OFFICIAL_DEFAULT_PROFILE_ID,
  getBuiltinProfile,
  type ThemeProfileRecipe,
} from '@/theme-engine';

/** Curated built-in presets shown on first-run theme pick. */
export const ONBOARDING_THEME_PRESET_IDS = [
  OFFICIAL_DEFAULT_PROFILE_ID,
  'preset-atkinson-calm',
  'preset-ocean',
] as const;

export type OnboardingThemePresetId = (typeof ONBOARDING_THEME_PRESET_IDS)[number];

export function getOnboardingThemePresets(): ThemeProfileRecipe[] {
  return ONBOARDING_THEME_PRESET_IDS.flatMap((id) => {
    const profile = getBuiltinProfile(id);
    return profile ? [profile] : [];
  });
}

export function isOnboardingThemePresetId(id: string): id is OnboardingThemePresetId {
  return (ONBOARDING_THEME_PRESET_IDS as readonly string[]).includes(id);
}
