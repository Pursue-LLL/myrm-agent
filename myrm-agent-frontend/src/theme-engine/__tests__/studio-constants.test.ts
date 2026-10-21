import { describe, expect, it } from 'vitest';
import {
  STUDIO_PREVIEW_PROFILE_ID,
  sanitizeActiveThemeProfileId,
  stripStudioPreviewProfiles,
} from '@/theme-engine/studio-constants';

describe('studio-constants', () => {
  it('strips ephemeral preview profile from library', () => {
    const profiles = [
      { id: 'studio/abc', name: 'Saved' },
      { id: STUDIO_PREVIEW_PROFILE_ID, name: 'Preview' },
    ];
    expect(stripStudioPreviewProfiles(profiles)).toEqual([{ id: 'studio/abc', name: 'Saved' }]);
  });

  it('resets active id when preview profile was persisted', () => {
    expect(sanitizeActiveThemeProfileId(STUDIO_PREVIEW_PROFILE_ID)).toBe('official-default');
    expect(sanitizeActiveThemeProfileId('studio/abc')).toBe('studio/abc');
  });
});
