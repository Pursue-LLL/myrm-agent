import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import { FUNCTIONAL_ART_WASH_FLOOR, FUNCTIONAL_ROUTE_PREFIXES, FUNCTIONAL_SURFACE_FLOORS } from '@/theme-engine';
import { THEME_PRE_INIT_SCRIPT } from '../theme-pre-init-script';

const publicScript = readFileSync(resolve(process.cwd(), 'public/theme-init.js'), 'utf8');

describe('theme-init public asset parity', () => {
  it('keeps public/theme-init.js aligned with THEME_PRE_INIT_SCRIPT keys', () => {
    for (const key of [
      'myrm-theme-preinit',
      'myrm-skin',
      'myrm-font',
      'theme-color',
      'data-myrm-theme-profile',
      'data-myrm-theme-layout',
      'data-myrm-theme-scene',
      'data-myrm-theme-art',
      'artPosterUrl',
      'myrm-theme-art-preload',
    ]) {
      expect(publicScript).toContain(key);
      expect(THEME_PRE_INIT_SCRIPT).toContain(key);
    }
  });

  it('embeds every functional route prefix from readability-scene SSOT', () => {
    for (const prefix of FUNCTIONAL_ROUTE_PREFIXES) {
      expect(THEME_PRE_INIT_SCRIPT).toContain(`'${prefix}'`);
      expect(publicScript).toContain(`'${prefix}'`);
    }
  });

  it('embeds functional surface opacity floors from scene-surfaces SSOT', () => {
    for (const script of [THEME_PRE_INIT_SCRIPT, publicScript]) {
      expect(script).toContain(String(FUNCTIONAL_SURFACE_FLOORS.navOpacity));
      expect(script).toContain(String(FUNCTIONAL_SURFACE_FLOORS.sidebarOpacity));
      expect(script).toContain(String(FUNCTIONAL_SURFACE_FLOORS.mainOpacity));
      expect(script).toContain(String(FUNCTIONAL_SURFACE_FLOORS.surfaceOpacity));
      expect(script).toContain(String(FUNCTIONAL_ART_WASH_FLOOR));
    }
  });
});
