import {
  BUILTIN_THEME_PROFILES,
  getDefaultThemeProfile,
  STUDIO_PREVIEW_PROFILE_ID,
  type ThemeProfileRecipe,
} from '@/theme-engine';

export { STUDIO_PREVIEW_PROFILE_ID };

export function allocateStudioProfileId(): string {
  return `studio/${crypto.randomUUID().replace(/-/g, '')}`;
}

export function createStudioDraft(base?: ThemeProfileRecipe): ThemeProfileRecipe {
  const seed = base ?? getDefaultThemeProfile();
  return {
    id: 'draft',
    name: base?.name ?? '',
    layoutId: seed.layoutId,
    fontId: seed.fontId,
    builtin: false,
    palette: { ...seed.palette },
    art: { ...seed.art },
    packageDescription: base?.packageDescription ?? null,
    packageTagline: base?.packageTagline ?? null,
    packageAuthor: base?.packageAuthor ?? null,
    packagePreviewAssetRef: base?.packagePreviewAssetRef ?? null,
  };
}

export function isEditableStudioProfile(profile: ThemeProfileRecipe): boolean {
  if (profile.builtin) {
    return false;
  }
  return (
    profile.id.startsWith('studio/') ||
    profile.id.startsWith('imported/') ||
    profile.id === STUDIO_PREVIEW_PROFILE_ID
  );
}

export function listManagedProfiles(profiles: ThemeProfileRecipe[]): ThemeProfileRecipe[] {
  return profiles.filter(
    (profile) =>
      profile.id.startsWith('studio/') ||
      profile.id.startsWith('imported/'),
  );
}

export function mergeProfileIntoLibrary(
  profiles: ThemeProfileRecipe[],
  profile: ThemeProfileRecipe,
): ThemeProfileRecipe[] {
  const without = profiles.filter((entry) => entry.id !== profile.id);
  return [...without, profile];
}

export function existingProfileIds(profiles: ThemeProfileRecipe[]): string[] {
  return [...BUILTIN_THEME_PROFILES.map((profile) => profile.id), ...profiles.map((p) => p.id)];
}
