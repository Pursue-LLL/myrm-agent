import { describe, it, expect, beforeEach } from 'vitest';
import {
  CURATED_DEVELOPER_THEMES,
  getCuratedThemeById,
} from '../curatedThemePresets';
import {
  useCuratedThemeStore,
  applyCuratedThemeVariables,
} from '../useCuratedThemeStore';

describe('curatedThemePresets & useCuratedThemeStore', () => {
  beforeEach(() => {
    useCuratedThemeStore.getState().resetToDefault();
    localStorage.clear();
  });

  it('contains 6 pro developer themes with complete tokens and ANSI palettes', () => {
    expect(CURATED_DEVELOPER_THEMES).toHaveLength(6);
    for (const theme of CURATED_DEVELOPER_THEMES) {
      expect(theme.id).toBeDefined();
      expect(theme.name).toBeDefined();
      expect(theme.contrastRatio).toContain('AAA');
      expect(theme.tokens.background).toBeDefined();
      expect(theme.tokens.foreground).toBeDefined();
      expect(theme.tokens.primary).toBeDefined();
      expect(theme.tokens.border).toBeDefined();
      expect(theme.ansi.black).toBeDefined();
      expect(theme.ansi.green).toBeDefined();
      expect(theme.ansi.cyan).toBeDefined();
      expect(theme.previewPalette).toHaveLength(5);
    }
  });

  it('retrieves theme correctly by ID', () => {
    const tokyo = getCuratedThemeById('tokyo-night');
    expect(tokyo).toBeDefined();
    expect(tokyo?.name).toBe('Tokyo Night');
    expect(tokyo?.tokens.background).toBe('#1a1b26');

    const dracula = getCuratedThemeById('dracula-pro');
    expect(dracula).toBeDefined();
    expect(dracula?.name).toBe('Dracula Pro');

    const unknown = getCuratedThemeById('default-dark');
    expect(unknown).toBeUndefined();
  });

  it('updates store state and persists to localStorage on setTheme', () => {
    useCuratedThemeStore.getState().setTheme('catppuccin-mocha');
    expect(useCuratedThemeStore.getState().activeThemeId).toBe('catppuccin-mocha');
    expect(localStorage.getItem('myrm_curated_developer_theme')).toBe('catppuccin-mocha');

    useCuratedThemeStore.getState().setTheme('nord');
    expect(useCuratedThemeStore.getState().activeThemeId).toBe('nord');
    expect(localStorage.getItem('myrm_curated_developer_theme')).toBe('nord');
  });

  it('injects CSS variables onto document root element without error', () => {
    const theme = getCuratedThemeById('tokyo-night');
    expect(theme).toBeDefined();
    if (theme) {
      applyCuratedThemeVariables(theme);
      expect(document.documentElement.getAttribute('data-curated-theme')).toBe('tokyo-night');
      expect(document.documentElement.style.getPropertyValue('--curated-bg')).toBe('#1a1b26');
      expect(document.documentElement.style.getPropertyValue('--curated-primary')).toBe('#7aa2f7');
    }

    applyCuratedThemeVariables(null);
    expect(document.documentElement.hasAttribute('data-curated-theme')).toBe(false);
    expect(document.documentElement.style.getPropertyValue('--curated-bg')).toBe('');
  });

  it('toggles sync with system dark mode preference', () => {
    useCuratedThemeStore.getState().setSyncWithSystemDark(false);
    expect(useCuratedThemeStore.getState().syncWithSystemDark).toBe(false);
    expect(localStorage.getItem('myrm_curated_theme_sync_system')).toBe('false');

    useCuratedThemeStore.getState().setSyncWithSystemDark(true);
    expect(useCuratedThemeStore.getState().syncWithSystemDark).toBe(true);
  });
});
