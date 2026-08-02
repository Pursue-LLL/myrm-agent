import { describe, expect, it, beforeEach } from 'vitest';
import useThemeStudioDomPreviewStore from '@/store/useThemeStudioDomPreviewStore';
import { getDefaultThemeProfile } from '@/theme-engine';

describe('useThemeStudioDomPreviewStore', () => {
  beforeEach(() => {
    useThemeStudioDomPreviewStore.getState().clearPreview();
  });

  it('activates preview without touching personal settings', () => {
    const profile = { ...getDefaultThemeProfile(), id: 'draft', name: 'Draft' };
    useThemeStudioDomPreviewStore.getState().setPreview({
      profile,
      mediaUrl: null,
      posterUrl: null,
    });
    const state = useThemeStudioDomPreviewStore.getState();
    expect(state.enabled).toBe(true);
    expect(state.profile?.name).toBe('Draft');
  });

  it('clears preview state on disable', () => {
    useThemeStudioDomPreviewStore.getState().setPreview({
      profile: getDefaultThemeProfile(),
      mediaUrl: 'https://example.com/a.png',
      posterUrl: 'https://example.com/a.png',
    });
    useThemeStudioDomPreviewStore.getState().clearPreview();
    const state = useThemeStudioDomPreviewStore.getState();
    expect(state.enabled).toBe(false);
    expect(state.profile).toBeNull();
  });
});
