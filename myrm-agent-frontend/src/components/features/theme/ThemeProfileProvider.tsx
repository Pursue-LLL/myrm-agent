/**
 * ConfigSync theme profile runtime: compile Recipe → DOM tokens, Art Layer, preinit snapshot.
 */
'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { usePathname } from 'next/navigation';
import { useTheme } from 'next-themes';
import useConfigStore from '@/store/useConfigStore';
import useThemeStudioDomPreviewStore from '@/store/useThemeStudioDomPreviewStore';
import { ensureFontLoaded } from '@/lib/fonts';
import {
  applyCompiledTheme,
  compileThemeProfile,
  getBuiltinProfile,
  getDefaultThemeProfile,
  mergeArtOverlay,
  EMPTY_THEME_PROFILES,
  resolveReadabilityScene,
  writeThemePreinitSnapshot,
  type CompiledTheme,
  type ThemeProfileRecipe,
} from '@/theme-engine';
import {
  resolveThemeAssetUrl,
  verifyThemeAssetAvailable,
} from '@/services/theme-assets/ThemeAssetStore';
import WorkspaceArtLayer from './WorkspaceArtLayer';
import ThemeAssetMissingBanner from './ThemeAssetMissingBanner';

function resolveActiveProfile(
  activeId: string | undefined,
  customProfiles: ThemeProfileRecipe[],
): ThemeProfileRecipe {
  let base: ThemeProfileRecipe;
  if (activeId) {
    const builtin = getBuiltinProfile(activeId);
    if (builtin) {
      base = builtin;
    } else {
      const custom = customProfiles.find((profile) => profile.id === activeId);
      base = custom ?? getDefaultThemeProfile();
    }
  } else {
    base = getDefaultThemeProfile();
  }
  return mergeArtOverlay(base, customProfiles);
}

const ThemeProfileProvider = ({ children }: { children: React.ReactNode }) => {
  const pathname = usePathname();
  const { resolvedTheme } = useTheme();
  const activeThemeProfileId = useConfigStore((s) => s.personalSettings?.activeThemeProfileId);
  const themeProfiles = useConfigStore(
    (s) => s.personalSettings?.themeProfiles ?? EMPTY_THEME_PROFILES,
  );
  const themeFontOverride = useConfigStore((s) => s.personalSettings?.themeFontOverride);

  const domPreviewEnabled = useThemeStudioDomPreviewStore((s) => s.enabled);
  const domPreviewProfile = useThemeStudioDomPreviewStore((s) => s.profile);
  const domPreviewMediaUrl = useThemeStudioDomPreviewStore((s) => s.mediaUrl);
  const domPreviewPosterUrl = useThemeStudioDomPreviewStore((s) => s.posterUrl);

  const configProfile = useMemo(() => {
    const base = resolveActiveProfile(activeThemeProfileId, themeProfiles);
    if (!themeFontOverride || themeFontOverride === base.fontId) return base;
    return { ...base, fontId: themeFontOverride };
  }, [activeThemeProfileId, themeProfiles, themeFontOverride]);

  const profile = domPreviewEnabled && domPreviewProfile ? domPreviewProfile : configProfile;

  const layoutId = profile.layoutId;

  const sceneId = useMemo(
    () => resolveReadabilityScene(pathname ?? '/'),
    [pathname],
  );

  const colorScheme = resolvedTheme === 'light' ? 'light' : 'dark';
  const prefersReducedMotion =
    typeof window !== 'undefined' &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const isMobile =
    typeof window !== 'undefined' && window.matchMedia('(max-width: 768px)').matches;

  const [mediaUrl, setMediaUrl] = useState<string | null>(null);
  const [posterUrl, setPosterUrl] = useState<string | null>(null);
  const [assetMissing, setAssetMissing] = useState(false);
  const objectUrlRef = useRef<string[]>([]);
  const assetLoadGenerationRef = useRef(0);

  useEffect(() => {
    if (domPreviewEnabled) {
      setMediaUrl(domPreviewMediaUrl);
      setPosterUrl(domPreviewPosterUrl);
      setAssetMissing(false);
      return;
    }

    const generation = assetLoadGenerationRef.current + 1;
    assetLoadGenerationRef.current = generation;

    let cancelled = false;
    const loadAssets = async () => {
      const needsBackground =
        profile.art.mediaKind !== 'none' && Boolean(profile.art.assetRef);

      const refsToVerify: string[] = [];
      if (needsBackground && profile.art.assetRef) {
        refsToVerify.push(profile.art.assetRef);
      }
      if (
        needsBackground &&
        profile.art.posterAssetRef &&
        profile.art.posterAssetRef !== profile.art.assetRef
      ) {
        refsToVerify.push(profile.art.posterAssetRef);
      }

      const availability = await Promise.all(
        refsToVerify.map((ref) => verifyThemeAssetAvailable(ref)),
      );
      const missing = refsToVerify.length > 0 && availability.some((ok) => !ok);

      const nextMedia = await resolveThemeAssetUrl(profile.art.assetRef);
      const nextPoster = await resolveThemeAssetUrl(profile.art.posterAssetRef);
      const resolvedPoster =
        nextPoster ?? (profile.art.mediaKind === 'image' ? nextMedia : null);

      if (cancelled || assetLoadGenerationRef.current !== generation) return;

      objectUrlRef.current.forEach((url) => URL.revokeObjectURL(url));
      objectUrlRef.current = [];
      if (nextMedia?.startsWith('blob:')) objectUrlRef.current.push(nextMedia);
      if (resolvedPoster?.startsWith('blob:') && resolvedPoster !== nextMedia) {
        objectUrlRef.current.push(resolvedPoster);
      }
      setMediaUrl(nextMedia);
      setPosterUrl(resolvedPoster);
      setAssetMissing(missing);
    };
    void loadAssets();
    return () => {
      cancelled = true;
    };
  }, [
    domPreviewEnabled,
    domPreviewMediaUrl,
    domPreviewPosterUrl,
    profile.art.assetRef,
    profile.art.mediaKind,
    profile.art.posterAssetRef,
  ]);

  const compiled: CompiledTheme = useMemo(
    () =>
      compileThemeProfile(
        profile,
        { colorScheme, layoutId, sceneId, prefersReducedMotion, isMobile },
        { mediaUrl, posterUrl },
      ),
    [profile, colorScheme, layoutId, sceneId, prefersReducedMotion, isMobile, mediaUrl, posterUrl],
  );

  useEffect(() => {
    ensureFontLoaded(compiled.fontId);
    applyCompiledTheme(document.documentElement, compiled);
    writeThemePreinitSnapshot(compiled, colorScheme, layoutId, sceneId, {
      artPosterUrl: posterUrl ?? (profile.art.mediaKind === 'image' ? mediaUrl : null),
      artWash: compiled.artLayer.wash,
    });
  }, [compiled, colorScheme, layoutId, sceneId, posterUrl, mediaUrl, profile.art.mediaKind]);

  useEffect(
    () => () => {
      objectUrlRef.current.forEach((url) => URL.revokeObjectURL(url));
    },
    [],
  );

  return (
    <>
      <WorkspaceArtLayer art={compiled.artLayer} />
      {!domPreviewEnabled && assetMissing ? <ThemeAssetMissingBanner /> : null}
      {children}
    </>
  );
};

export default ThemeProfileProvider;
