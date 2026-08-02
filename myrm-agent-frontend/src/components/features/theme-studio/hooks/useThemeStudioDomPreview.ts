'use client';

import { useEffect } from 'react';
import useThemeStudioDomPreviewStore from '@/store/useThemeStudioDomPreviewStore';
import { resolveThemeAssetUrl } from '@/services/theme-assets/ThemeAssetStore';
import type { ThemeProfileRecipe } from '@/theme-engine';

/**
 * Workspace live preview via DOM compile only — never writes personalSettings / ConfigSync.
 */
export function useThemeStudioDomPreview(
  enabled: boolean,
  previewProfile: ThemeProfileRecipe | null,
  draftPreviewAssetUrl: string | null,
): void {
  const setPreview = useThemeStudioDomPreviewStore((state) => state.setPreview);
  const clearPreview = useThemeStudioDomPreviewStore((state) => state.clearPreview);

  useEffect(() => {
    if (!enabled || !previewProfile) {
      clearPreview();
      return;
    }

    let cancelled = false;

    const applyPreview = async () => {
      let mediaUrl: string | null = null;
      let posterUrl: string | null = null;

      if (previewProfile.art.assetRef) {
        if (previewProfile.art.mediaKind === 'video') {
          mediaUrl = await resolveThemeAssetUrl(previewProfile.art.assetRef);
          posterUrl =
            (await resolveThemeAssetUrl(previewProfile.art.posterAssetRef)) ??
            draftPreviewAssetUrl ??
            mediaUrl;
        } else {
          mediaUrl =
            draftPreviewAssetUrl ?? (await resolveThemeAssetUrl(previewProfile.art.assetRef));
          posterUrl = mediaUrl;
        }
      }

      if (cancelled) {
        return;
      }

      setPreview({ profile: previewProfile, mediaUrl, posterUrl });
    };

    void applyPreview();

    return () => {
      cancelled = true;
      clearPreview();
    };
  }, [clearPreview, draftPreviewAssetUrl, enabled, previewProfile, setPreview]);
}
