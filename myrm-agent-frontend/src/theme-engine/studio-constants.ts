/** Ephemeral Theme Studio live-preview profile id — must never persist in ConfigSync. */
export const STUDIO_PREVIEW_PROFILE_ID = 'studio/__preview__';

export function stripStudioPreviewProfiles<T extends { id: string }>(profiles: T[]): T[] {
  return profiles.filter((profile) => profile.id !== STUDIO_PREVIEW_PROFILE_ID);
}

export function sanitizeActiveThemeProfileId(activeId: string | undefined): string | undefined {
  if (activeId === STUDIO_PREVIEW_PROFILE_ID) {
    return 'official-default';
  }
  return activeId;
}
