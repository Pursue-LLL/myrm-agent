import type { FontId } from '@/lib/fonts';
import { getFontStack } from '@/lib/fonts';
import { resolveContrastSafeForeground } from './oklch';
import { effectiveArtWash, mergeSceneSurfaces } from './scene-surfaces';
import type { CompiledTheme, CompiledThemeArtLayer, ThemeCompileContext, ThemeProfileRecipe } from './schema';

export interface ThemeAssetUrls {
  mediaUrl: string | null;
  posterUrl: string | null;
}

function pickPrimary(recipe: ThemeProfileRecipe, colorScheme: 'light' | 'dark') {
  const isDark = colorScheme === 'dark';
  const primary = isDark ? recipe.palette.primaryDark : recipe.palette.primaryLight;
  const primaryHover = isDark ? recipe.palette.primaryHoverDark : recipe.palette.primaryHoverLight;
  const primaryDark = isDark ? recipe.palette.primaryDarkDark : recipe.palette.primaryDarkLight;
  const accentWarm = recipe.palette.dualAccent
    ? isDark
      ? (recipe.palette.accentWarmDark ?? primary)
      : (recipe.palette.accentWarmLight ?? primary)
    : primary;
  const primaryForeground = resolveContrastSafeForeground(primary);
  const accentWarmForeground = resolveContrastSafeForeground(accentWarm);
  return { primary, primaryHover, primaryDark, accentWarm, primaryForeground, accentWarmForeground };
}

function buildBrandShadows(primary: string, accentWarm: string, dual: boolean): Record<string, string> {
  const warm = dual ? accentWarm : primary;
  return {
    '--brand-gradient': dual
      ? `linear-gradient(135deg, ${primary} 0%, ${primary} 50%, color-mix(in srgb, ${primary} 55%, ${accentWarm}) 78%, ${accentWarm} 100%)`
      : `linear-gradient(180deg, ${primary} 0%, var(--primary-hover) 100%)`,
    '--brand-gradient-subtle': dual
      ? `linear-gradient(135deg, color-mix(in srgb, ${primary} 14%, transparent) 0%, color-mix(in srgb, ${primary} 8%, transparent) 72%, color-mix(in srgb, ${accentWarm} 10%, transparent) 100%)`
      : `linear-gradient(135deg, color-mix(in srgb, ${primary} 14%, transparent) 0%, color-mix(in srgb, ${primary} 8%, transparent) 100%)`,
    '--brand-gradient-border': dual
      ? `linear-gradient(135deg, color-mix(in srgb, ${primary} 42%, transparent) 0%, color-mix(in srgb, ${accentWarm} 28%, transparent) 100%)`
      : `linear-gradient(135deg, color-mix(in srgb, ${primary} 45%, transparent) 0%, color-mix(in srgb, ${primary} 28%, transparent) 100%)`,
    '--shadow-brand': `0 6px 14px color-mix(in srgb, ${warm} 22%, transparent)`,
    '--shadow-brand-lg': `0 12px 24px color-mix(in srgb, ${warm} 14%, transparent)`,
    '--shadow-brand-sm': `0 2px 10px color-mix(in srgb, ${warm} 14%, transparent)`,
    '--shadow-brand-inset': `inset 0 1px 0 color-mix(in srgb, ${warm} 18%, transparent)`,
  };
}

function isVideoMimeUrl(url: string | null): boolean {
  if (!url) {
    return false;
  }
  const lower = url.toLowerCase();
  return lower.includes('.mp4') || lower.includes('video/mp4');
}

function buildArtLayer(
  recipe: ThemeProfileRecipe,
  context: ThemeCompileContext,
  assetUrls: ThemeAssetUrls,
): CompiledThemeArtLayer {
  const surfaces = mergeSceneSurfaces(context.layoutId, context.sceneId);
  const isVideoSource = recipe.art.mediaKind === 'video';
  const posterUrl = assetUrls.posterUrl;
  const mediaUrl = assetUrls.mediaUrl;
  const staticImageUrl =
    posterUrl ?? (recipe.art.mediaKind === 'image' && mediaUrl && !isVideoMimeUrl(mediaUrl) ? mediaUrl : null);

  const canPlayVideo = isVideoSource && Boolean(mediaUrl) && !context.prefersReducedMotion && !context.isMobile;

  const useVideo = canPlayVideo;
  const enabled = recipe.art.mediaKind !== 'none' && Boolean(useVideo ? mediaUrl : staticImageUrl);

  let displayMediaKind = recipe.art.mediaKind;
  let displayMediaUrl: string | null = null;
  let displayPosterUrl: string | null = staticImageUrl;

  if (useVideo && mediaUrl) {
    displayMediaKind = 'video';
    displayMediaUrl = mediaUrl;
    displayPosterUrl = posterUrl ?? null;
  } else if (isVideoSource) {
    displayMediaKind = 'image';
    displayMediaUrl = staticImageUrl;
    displayPosterUrl = staticImageUrl;
  } else if (recipe.art.mediaKind === 'image') {
    displayMediaKind = 'image';
    displayMediaUrl = staticImageUrl;
    displayPosterUrl = staticImageUrl;
  }

  return {
    enabled,
    mediaKind: displayMediaKind,
    mediaUrl: displayMediaUrl,
    posterUrl: displayPosterUrl,
    focusX: recipe.art.focusX,
    focusY: recipe.art.focusY,
    wash: effectiveArtWash(recipe.art.wash, context.sceneId),
    surfaceOpacity: surfaces.surfaceOpacity,
    navOpacity: surfaces.navOpacity,
    sidebarOpacity: surfaces.sidebarOpacity,
    mainOpacity: surfaces.mainOpacity,
  };
}

export function compileThemeProfile(
  recipe: ThemeProfileRecipe,
  context: ThemeCompileContext,
  assetUrls: ThemeAssetUrls = { mediaUrl: null, posterUrl: null },
): CompiledTheme {
  const { primary, primaryHover, primaryDark, accentWarm, primaryForeground, accentWarmForeground } = pickPrimary(
    recipe,
    context.colorScheme,
  );
  const dual = recipe.palette.dualAccent;
  const brand = buildBrandShadows(primary, accentWarm, dual);
  const artLayer = buildArtLayer(recipe, context, assetUrls);

  const cssVariables: Record<string, string> = {
    '--primary': primary,
    '--primary-foreground': primaryForeground,
    '--primary-hover': primaryHover,
    '--primary-dark': primaryDark,
    '--ring': primary,
    '--accent-warm': accentWarm,
    '--accent-warm-foreground': accentWarmForeground,
    '--button-fill': dual ? accentWarm : primary,
    '--button-fill-hover': dual ? (context.colorScheme === 'dark' ? '#ffc47a' : '#c96a28') : primaryHover,
    '--button-fill-foreground': dual ? accentWarmForeground : primaryForeground,
    '--myrm-theme-nav-opacity': String(artLayer.navOpacity),
    '--myrm-theme-sidebar-opacity': String(artLayer.sidebarOpacity),
    '--myrm-theme-main-opacity': String(artLayer.mainOpacity),
    '--myrm-theme-surface-opacity': String(artLayer.surfaceOpacity),
    '--myrm-theme-art-wash': String(artLayer.wash),
    '--myrm-theme-art-focus-x': `${artLayer.focusX * 100}%`,
    '--myrm-theme-art-focus-y': `${artLayer.focusY * 100}%`,
    ...brand,
  };

  if (!dual) {
    cssVariables['--brand-mix'] = primary;
  }

  const dataAttributes: Record<string, string> = {
    'data-myrm-theme-profile': recipe.id,
    'data-myrm-theme-layout': context.layoutId,
    'data-myrm-theme-scene': context.sceneId,
    'data-myrm-theme-art': artLayer.enabled ? 'on' : 'off',
    'data-myrm-theme-dual-accent': dual ? 'true' : 'false',
  };

  return {
    cssVariables,
    dataAttributes,
    artLayer,
    fontId: recipe.fontId,
  };
}

export function applyCompiledTheme(root: HTMLElement, compiled: CompiledTheme): void {
  for (const [name, value] of Object.entries(compiled.cssVariables)) {
    root.style.setProperty(name, value);
  }
  for (const [name, value] of Object.entries(compiled.dataAttributes)) {
    root.setAttribute(name, value);
  }
  applyThemeFont(root, compiled.fontId);
}

export function applyThemeFont(root: HTMLElement, fontId: FontId): void {
  if (fontId === 'inter') {
    root.style.removeProperty('--font-override');
    root.removeAttribute('data-font');
    return;
  }
  root.style.setProperty('--font-override', getFontStack(fontId));
  root.setAttribute('data-font', fontId);
}

export function clearThemeRuntime(root: HTMLElement): void {
  const runtimeKeys = [
    '--primary',
    '--primary-foreground',
    '--primary-hover',
    '--primary-dark',
    '--ring',
    '--accent-warm',
    '--accent-warm-foreground',
    '--button-fill',
    '--button-fill-hover',
    '--button-fill-foreground',
    '--brand-gradient',
    '--brand-gradient-subtle',
    '--brand-gradient-border',
    '--shadow-brand',
    '--shadow-brand-lg',
    '--shadow-brand-sm',
    '--shadow-brand-inset',
    '--myrm-theme-nav-opacity',
    '--myrm-theme-sidebar-opacity',
    '--myrm-theme-main-opacity',
    '--myrm-theme-surface-opacity',
    '--myrm-theme-art-wash',
    '--myrm-theme-art-focus-x',
    '--myrm-theme-art-focus-y',
    '--brand-mix',
  ];
  for (const key of runtimeKeys) {
    root.style.removeProperty(key);
  }
  root.removeAttribute('data-myrm-theme-profile');
  root.removeAttribute('data-myrm-theme-layout');
  root.removeAttribute('data-myrm-theme-scene');
  root.removeAttribute('data-myrm-theme-art');
  root.removeAttribute('data-myrm-theme-dual-accent');
}
