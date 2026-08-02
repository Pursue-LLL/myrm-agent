import { describe, expect, it } from 'vitest';
import { compileThemeProfile } from '../compiler';
import { contrastRatio, meetsContrast } from '../oklch';
import { getDefaultThemeProfile } from '../presets';
import { resolveLayoutFromPathname } from '../route-layout';

describe('theme-engine compiler', () => {
  it('compiles official default for light and dark', () => {
    const profile = getDefaultThemeProfile();
    const light = compileThemeProfile(profile, {
      colorScheme: 'light',
      layoutId: 'full-bleed',
      prefersReducedMotion: false,
      isMobile: false,
    });
    const dark = compileThemeProfile(profile, {
      colorScheme: 'dark',
      layoutId: 'full-bleed',
      prefersReducedMotion: false,
      isMobile: false,
    });
    expect(light.cssVariables['--primary']).toBe('#588e95');
    expect(dark.cssVariables['--primary']).toBe('#6ba3aa');
    expect(light.dataAttributes['data-myrm-theme-dual-accent']).toBe('true');
    // Official light primary (#588e95) + foreground (#fbfbf8) ≈ 3.54:1 — below WCAG AA 4.5 (OKLCh auto-foreground deferred #8).
    expect(contrastRatio(light.cssVariables['--primary-foreground'], light.cssVariables['--primary'])).toBeGreaterThan(3);
    expect(meetsContrast(dark.cssVariables['--primary-foreground'], dark.cssVariables['--primary'])).toBe(true);
  });

  it('uses work-dense surfaces on kanban routes', () => {
    const layout = resolveLayoutFromPathname('/kanban', 'full-bleed');
    expect(layout).toBe('work-dense');
    const profile = getDefaultThemeProfile();
    const compiled = compileThemeProfile(profile, {
      colorScheme: 'dark',
      layoutId: layout,
      prefersReducedMotion: false,
      isMobile: false,
    });
    expect(Number(compiled.artLayer.surfaceOpacity)).toBeGreaterThan(0.9);
  });

  it('keeps art wash independent from layout wash floor', () => {
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
    const compiled = compileThemeProfile(
      withArt,
      {
        colorScheme: 'dark',
        layoutId: 'work-dense',
        prefersReducedMotion: false,
        isMobile: false,
      },
      { mediaUrl: 'https://cdn.example.com/hero.png', posterUrl: 'https://cdn.example.com/hero.png' },
    );
    expect(compiled.artLayer.wash).toBe(0.25);
    expect(Number(compiled.cssVariables['--myrm-theme-surface-opacity'])).toBeGreaterThan(0.9);
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
