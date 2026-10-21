/**
 * Theme-field change detection for personalSettings ConfigSync fast-path.
 *
 * [INPUT]
 * services/config/configFingerprint::valuesEqual (POS: stable canonical fingerprint / deep equal)
 * services/config/types::PersonalSettingsConfigValue (POS: personalSettings 配置值类型)
 *
 * [OUTPUT]
 * isThemePersonalSettingsChange: 检测 activeThemeProfileId / themeProfiles / themeFontOverride 是否变更
 *
 * [POS]
 * ConfigSync 主题持久化辅助。供 ConfigSyncManager.set 决定是否跳过 debounce 立即 flush。
 */
import { valuesEqual } from './configFingerprint';
import { DEFAULT_PERSONAL_SETTINGS, type PersonalSettingsConfigValue } from './types';

type ThemePersonalSettingsSlice = Pick<
  PersonalSettingsConfigValue,
  'activeThemeProfileId' | 'themeProfiles' | 'themeFontOverride'
>;

function pickThemeSlice(value: PersonalSettingsConfigValue | undefined): ThemePersonalSettingsSlice {
  if (!value) {
    return {};
  }
  return {
    activeThemeProfileId: value.activeThemeProfileId,
    themeProfiles: value.themeProfiles,
    themeFontOverride: value.themeFontOverride,
  };
}

export function isThemePersonalSettingsChange(
  previous: PersonalSettingsConfigValue | undefined,
  next: PersonalSettingsConfigValue,
): boolean {
  const baseline = previous ?? DEFAULT_PERSONAL_SETTINGS;
  return !valuesEqual(pickThemeSlice(baseline), pickThemeSlice(next));
}
