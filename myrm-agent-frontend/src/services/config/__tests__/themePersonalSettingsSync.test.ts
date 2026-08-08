import { describe, expect, it } from 'vitest';
import { isThemePersonalSettingsChange } from '@/services/config/themePersonalSettingsSync';
import { DEFAULT_PERSONAL_SETTINGS, type PersonalSettingsConfigValue } from '@/services/config/types';
import { getDefaultThemeProfile } from '@/theme-engine/presets';

const base = (): PersonalSettingsConfigValue => ({ ...DEFAULT_PERSONAL_SETTINGS });

describe('isThemePersonalSettingsChange', () => {
  it('returns false when cache is empty and only non-theme fields change from defaults', () => {
    const next = { ...base(), systemInstructions: 'hello' };
    expect(isThemePersonalSettingsChange(undefined, next)).toBe(false);
  });

  it('returns true when cache is empty but theme differs from defaults', () => {
    const next = { ...base(), activeThemeProfileId: 'ocean-blue' };
    expect(isThemePersonalSettingsChange(undefined, next)).toBe(true);
  });

  it('returns false when theme fields are unchanged', () => {
    const prev = { ...base(), activeThemeProfileId: 'official-default' };
    const next = { ...prev, systemInstructions: 'updated' };
    expect(isThemePersonalSettingsChange(prev, next)).toBe(false);
  });

  it('returns true when activeThemeProfileId changes', () => {
    const prev = base();
    const next = { ...prev, activeThemeProfileId: 'ocean-blue' };
    expect(isThemePersonalSettingsChange(prev, next)).toBe(true);
  });

  it('returns true when themeProfiles changes', () => {
    const prev = base();
    const next = {
      ...prev,
      themeProfiles: [getDefaultThemeProfile()],
    };
    expect(isThemePersonalSettingsChange(prev, next)).toBe(true);
  });

  it('returns true when themeFontOverride changes', () => {
    const prev = base();
    const next = { ...prev, themeFontOverride: 'system' as const };
    expect(isThemePersonalSettingsChange(prev, next)).toBe(true);
  });
});
