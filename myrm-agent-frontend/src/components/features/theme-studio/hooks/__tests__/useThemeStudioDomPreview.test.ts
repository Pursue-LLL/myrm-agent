import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { useThemeStudioDomPreview } from '@/components/features/theme-studio/hooks/useThemeStudioDomPreview';
import useThemeStudioDomPreviewStore from '@/store/useThemeStudioDomPreviewStore';
import useConfigStore from '@/store/useConfigStore';
import { getDefaultThemeProfile } from '@/theme-engine';

vi.mock('@/services/theme-assets/ThemeAssetStore', () => ({
  resolveThemeAssetUrl: vi.fn().mockResolvedValue(null),
}));

describe('useThemeStudioDomPreview', () => {
  beforeEach(() => {
    useThemeStudioDomPreviewStore.getState().clearPreview();
    vi.clearAllMocks();
  });

  it('does not write personalSettings / ConfigSync while preview is active', async () => {
    const updatePersonalSettings = vi.fn();
    vi.spyOn(useConfigStore, 'getState').mockReturnValue({
      ...useConfigStore.getState(),
      updatePersonalSettings,
    });

    const profile = { ...getDefaultThemeProfile(), id: 'draft', name: 'Draft preview' };

    renderHook(({ enabled }) => useThemeStudioDomPreview(enabled, profile, null), {
      initialProps: { enabled: true },
    });

    await waitFor(() => {
      expect(useThemeStudioDomPreviewStore.getState().enabled).toBe(true);
    });

    expect(updatePersonalSettings).not.toHaveBeenCalled();
  });

  it('clears dom preview store when disabled', async () => {
    const profile = { ...getDefaultThemeProfile(), id: 'draft', name: 'Draft preview' };

    const { rerender } = renderHook(({ enabled }) => useThemeStudioDomPreview(enabled, profile, null), {
      initialProps: { enabled: true },
    });

    await waitFor(() => {
      expect(useThemeStudioDomPreviewStore.getState().enabled).toBe(true);
    });

    rerender({ enabled: false });

    await waitFor(() => {
      expect(useThemeStudioDomPreviewStore.getState().enabled).toBe(false);
    });
  });
});
