import { describe, expect, it } from 'vitest';
import { compileThemeProfile } from '../compiler';
import { BUILTIN_THEME_PROFILES, getDefaultThemeProfile } from '../presets';
import { resolveReadabilityScene, FUNCTIONAL_ROUTE_PREFIXES } from '../readability-scene';
import { effectiveArtWash, FUNCTIONAL_ART_WASH_FLOOR, FUNCTIONAL_SURFACE_FLOORS } from '../scene-surfaces';
import { meetsContrast } from '../oklch';

describe('theme-engine compiler', () => {
  it('all builtin presets meet WCAG AA for primary and button foreground', () => {
    for (const profile of BUILTIN_THEME_PROFILES) {
      for (const colorScheme of ['light', 'dark'] as const) {
        const compiled = compileThemeProfile(profile, {
          colorScheme,
          layoutId: profile.layoutId,
          sceneId: 'immersive',
          prefersReducedMotion: false,
          isMobile: false,
        });
        const pairs: [string, string][] = [
          [compiled.cssVariables['--primary-foreground'], compiled.cssVariables['--primary']],
          [compiled.cssVariables['--button-fill-foreground'], compiled.cssVariables['--button-fill']],
        ];
        for (const [foreground, background] of pairs) {
          expect(meetsContrast(foreground, background)).toBe(true);
        }
      }
    }
  });

  it('compiles official default for light and dark with WCAG AA foreground', () => {
    const profile = getDefaultThemeProfile();
    const light = compileThemeProfile(profile, {
      colorScheme: 'light',
      layoutId: 'full-bleed',
      sceneId: 'immersive',
      prefersReducedMotion: false,
      isMobile: false,
    });
    const dark = compileThemeProfile(profile, {
      colorScheme: 'dark',
      layoutId: 'full-bleed',
      sceneId: 'immersive',
      prefersReducedMotion: false,
      isMobile: false,
    });
    expect(light.cssVariables['--primary']).toBe('#588e95');
    expect(dark.cssVariables['--primary']).toBe('#6ba3aa');
    expect(light.dataAttributes['data-myrm-theme-dual-accent']).toBe('true');
    expect(meetsContrast(light.cssVariables['--primary-foreground'], light.cssVariables['--primary'])).toBe(true);
    expect(meetsContrast(dark.cssVariables['--primary-foreground'], dark.cssVariables['--primary'])).toBe(true);
  });

  it('uses functional scene surfaces on kanban without replacing layout id', () => {
    expect(resolveReadabilityScene('/kanban')).toBe('functional');
    const profile = getDefaultThemeProfile();
    const compiled = compileThemeProfile(profile, {
      colorScheme: 'dark',
      layoutId: 'full-bleed',
      sceneId: 'functional',
      prefersReducedMotion: false,
      isMobile: false,
    });
    expect(compiled.dataAttributes['data-myrm-theme-layout']).toBe('full-bleed');
    expect(compiled.dataAttributes['data-myrm-theme-scene']).toBe('functional');
    expect(compiled.artLayer.surfaceOpacity).toBeGreaterThanOrEqual(FUNCTIONAL_SURFACE_FLOORS.surfaceOpacity);
    expect(compiled.artLayer.mainOpacity).toBeGreaterThanOrEqual(FUNCTIONAL_SURFACE_FLOORS.mainOpacity);
  });

  it('raises art wash floor on functional scene only', () => {
    const profile = getDefaultThemeProfile();
    const withArt = {
      ...profile,
      art: {
        ...profile.art,
        mediaKind: 'image' as const,
        assetRef: 'file:img',
        wash: 0.25,
      },
    };
    const immersive = compileThemeProfile(
      withArt,
      {
        colorScheme: 'dark',
        layoutId: 'full-bleed',
        sceneId: 'immersive',
        prefersReducedMotion: false,
        isMobile: false,
      },
      { mediaUrl: 'https://cdn.example.com/hero.png', posterUrl: 'https://cdn.example.com/hero.png' },
    );
    const functional = compileThemeProfile(
      withArt,
      {
        colorScheme: 'dark',
        layoutId: 'full-bleed',
        sceneId: 'functional',
        prefersReducedMotion: false,
        isMobile: false,
      },
      { mediaUrl: 'https://cdn.example.com/hero.png', posterUrl: 'https://cdn.example.com/hero.png' },
    );
    expect(immersive.artLayer.wash).toBe(0.25);
    expect(functional.artLayer.enabled).toBe(true);
    expect(functional.artLayer.wash).toBe(effectiveArtWash(0.25, 'functional'));
    expect(functional.artLayer.wash).toBeGreaterThanOrEqual(FUNCTIONAL_ART_WASH_FLOOR);
    expect(functional.artLayer.surfaceOpacity).toBeGreaterThanOrEqual(FUNCTIONAL_SURFACE_FLOORS.surfaceOpacity);
    expect(functional.artLayer.navOpacity).toBeGreaterThanOrEqual(FUNCTIONAL_SURFACE_FLOORS.navOpacity);
  });

  it('downgrades mobile video to poster image without mp4 background', () => {
    const profile = getDefaultThemeProfile();
    const withVideo = {
      ...profile,
      art: {
        ...profile.art,
        mediaKind: 'video' as const,
        assetRef: 'file:video',
        posterAssetRef: 'file:poster',
        wash: 0.4,
      },
    };
    const compiled = compileThemeProfile(
      withVideo,
      {
        colorScheme: 'dark',
        layoutId: 'full-bleed',
        sceneId: 'immersive',
        prefersReducedMotion: false,
        isMobile: true,
      },
      {
        mediaUrl: 'https://cdn.example.com/loop.mp4',
        posterUrl: 'https://cdn.example.com/poster.jpg',
      },
    );
    expect(compiled.artLayer.enabled).toBe(true);
    expect(compiled.artLayer.mediaKind).toBe('image');
    expect(compiled.artLayer.mediaUrl).toBe('https://cdn.example.com/poster.jpg');
    expect(compiled.artLayer.posterUrl).toBe('https://cdn.example.com/poster.jpg');
  });

  it('disables art when video has no poster on mobile', () => {
    const profile = getDefaultThemeProfile();
    const withVideo = {
      ...profile,
      art: {
        ...profile.art,
        mediaKind: 'video' as const,
        assetRef: 'file:video',
        posterAssetRef: null,
        wash: 0.4,
      },
    };
    const compiled = compileThemeProfile(
      withVideo,
      {
        colorScheme: 'dark',
        layoutId: 'full-bleed',
        sceneId: 'immersive',
        prefersReducedMotion: false,
        isMobile: true,
      },
      {
        mediaUrl: 'https://cdn.example.com/loop.mp4',
        posterUrl: null,
      },
    );
    expect(compiled.artLayer.enabled).toBe(false);
  });
});

describe('functional route registry parity', () => {
  it('does not include phantom /memory or /approvals prefixes', () => {
    expect(FUNCTIONAL_ROUTE_PREFIXES).not.toContain('/memory');
    expect(FUNCTIONAL_ROUTE_PREFIXES).not.toContain('/approvals');
  });

  it('covers brain and library feature pages', () => {
    expect(resolveReadabilityScene('/brain')).toBe('functional');
    expect(resolveReadabilityScene('/library')).toBe('functional');
  });
});
