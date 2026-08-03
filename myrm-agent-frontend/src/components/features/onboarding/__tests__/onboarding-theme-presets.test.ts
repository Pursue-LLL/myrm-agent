import { describe, expect, it } from 'vitest';
import {
  ONBOARDING_THEME_PRESET_IDS,
  getOnboardingThemePresets,
  isOnboardingThemePresetId,
} from '../onboarding-theme-presets';

describe('onboarding-theme-presets', () => {
  it('exposes three curated built-in presets', () => {
    expect(ONBOARDING_THEME_PRESET_IDS).toHaveLength(3);
    expect(getOnboardingThemePresets()).toHaveLength(3);
  });

  it('validates onboarding preset ids', () => {
    expect(isOnboardingThemePresetId('official-default')).toBe(true);
    expect(isOnboardingThemePresetId('preset-ocean')).toBe(true);
    expect(isOnboardingThemePresetId('unknown')).toBe(false);
  });
});
