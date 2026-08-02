import { describe, expect, it } from 'vitest';
import { compileThemeProfile } from '../compiler';
import { getDefaultThemeProfile } from '../presets';
import { resolveReadabilityScene, FUNCTIONAL_ROUTE_PREFIXES } from '../readability-scene';
import { effectiveArtWash } from '../scene-surfaces';
import { meetsContrast } from '../oklch';

describe('theme-engine compiler', () => {
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
    expect(
      meetsContrast(light.cssVariables['--primary-foreground'], light.cssVariables['--primary']),
    ).toBe(true);
    expect(meetsContrast(dark.cssVariables['--primary-foreground'], dark.cssVariables['--primary'])).toBe(
      true,
    );
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
    expect(Number(compiled.artLayer.surfaceOpacity)).toBeGreaterThan(0.9);
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
    expect(functional.artLayer.wash).toBe(effectiveArtWash(0.25, 'functional'));
    expect(functional.artLayer.wash).toBeGreaterThan(0.25);
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
