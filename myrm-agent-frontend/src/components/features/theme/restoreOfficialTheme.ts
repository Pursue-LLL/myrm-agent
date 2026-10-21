import useConfigStore from '@/store/useConfigStore';
import useThemeStudioDraftStore from '@/store/useThemeStudioDraftStore';
import useThemeStudioDomPreviewStore from '@/store/useThemeStudioDomPreviewStore';
import {
  buildOfficialThemeRestorePatch,
  isThemeDeviatedFromOfficial,
  needsRestoreConfirm,
  EMPTY_THEME_PROFILES,
  type ThemeRestoreState,
} from '@/theme-engine';

export async function executeOfficialThemeRestore(): Promise<void> {
  const updatePersonalSettings = useConfigStore.getState().updatePersonalSettings;
  await updatePersonalSettings(buildOfficialThemeRestorePatch());
  useThemeStudioDraftStore.getState().resetDraft();
  useThemeStudioDomPreviewStore.getState().clearPreview();
}

export function readThemeRestoreState(): ThemeRestoreState {
  const personalSettings = useConfigStore.getState().personalSettings;
  return {
    activeThemeProfileId: personalSettings?.activeThemeProfileId,
    themeProfiles: personalSettings?.themeProfiles ?? EMPTY_THEME_PROFILES,
    themeFontOverride: personalSettings?.themeFontOverride,
  };
}

export function canRestoreOfficialTheme(state: ThemeRestoreState = readThemeRestoreState()): boolean {
  return isThemeDeviatedFromOfficial(state);
}

export function shouldConfirmOfficialThemeRestore(state: ThemeRestoreState = readThemeRestoreState()): boolean {
  return needsRestoreConfirm(state);
}
