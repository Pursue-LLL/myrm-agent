import { describe, expect, it } from 'vitest';
import {
  allocateStudioProfileId,
  createStudioDraft,
  listManagedProfiles,
} from '@/components/features/theme-studio/studio-profile';
import { compileThemeProfile, getDefaultThemeProfile } from '@/theme-engine';

describe('studio-profile', () => {
  it('allocates unique studio ids', () => {
    const a = allocateStudioProfileId();
    const b = allocateStudioProfileId();
    expect(a).toMatch(/^studio\//);
    expect(a).not.toEqual(b);
  });

  it('lists managed imported and studio profiles only', () => {
    const profiles = listManagedProfiles([
      {
        ...getDefaultThemeProfile(),
        id: 'studio/abc',
        name: 'Studio',
        builtin: false,
      },
      {
        ...getDefaultThemeProfile(),
        id: 'imported/def',
        name: 'Imported',
        builtin: false,
      },
      {
        ...getDefaultThemeProfile(),
        id: 'user-art-overlay',
        name: 'Overlay',
        builtin: false,
      },
    ]);
    expect(profiles).toHaveLength(2);
  });
});

describe('theme studio compile parity', () => {
  it('matches provider compile path for draft profile', () => {
    const draft = createStudioDraft();
    draft.palette.primaryLight = '#112233';
    const compiled = compileThemeProfile(draft, {
      colorScheme: 'light',
      layoutId: draft.layoutId,
      sceneId: 'immersive',
      prefersReducedMotion: false,
      isMobile: false,
    });
    expect(compiled.cssVariables['--primary']).toBeTruthy();
    expect(compiled.artLayer.wash).toBeGreaterThan(0);
  });
});
