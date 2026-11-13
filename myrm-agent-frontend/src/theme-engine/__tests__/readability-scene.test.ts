import { existsSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';
import { describe, expect, it } from 'vitest';
import {
  FUNCTIONAL_ROUTE_PREFIXES,
  IMMERSIVE_EXACT_PATHS,
  STATIC_APP_SEGMENTS,
  resolveReadabilityScene,
} from '../readability-scene';

// The desktop pet overlay is a transparent window: it never shows the app's wallpaper or chrome, so it has no scene.
const SCENELESS_APP_SEGMENTS = new Set(['pet-overlay']);

describe('readability-scene', () => {
  it('treats chat roots as immersive', () => {
    for (const path of IMMERSIVE_EXACT_PATHS) {
      expect(resolveReadabilityScene(path)).toBe('immersive');
    }
  });

  it('treats dynamic chat session paths as immersive', () => {
    expect(resolveReadabilityScene('/550e8400-e29b-41d4-a716-446655440000')).toBe('immersive');
  });

  it('treats kanban and settings as functional', () => {
    expect(resolveReadabilityScene('/kanban')).toBe('functional');
    expect(resolveReadabilityScene('/settings/memory')).toBe('functional');
  });

  it.each(['/batch-directories', '/research', '/runs'])(
    'treats the single-segment page %s as functional, not as a chat session',
    (path) => {
      expect(resolveReadabilityScene(path)).toBe('functional');
    },
  );

  it('classifies every top-level page of the app router, so none is mistaken for a chat session', () => {
    const appDir = resolve(process.cwd(), 'src/app');
    const pageSegments = readdirSync(appDir, { withFileTypes: true })
      .filter((entry) => entry.isDirectory() && !/^[[(_]/.test(entry.name))
      .map((entry) => entry.name)
      .filter((segment) => existsSync(resolve(appDir, segment, 'page.tsx')) && !SCENELESS_APP_SEGMENTS.has(segment));

    expect(pageSegments.filter((segment) => !STATIC_APP_SEGMENTS.has(segment))).toEqual([]);
  });

  it('normalizes trailing slashes', () => {
    expect(resolveReadabilityScene('/kanban/')).toBe('functional');
    expect(resolveReadabilityScene('/chat/')).toBe('immersive');
  });

  it('exports functional prefixes used by preinit script', () => {
    expect(FUNCTIONAL_ROUTE_PREFIXES.length).toBeGreaterThan(10);
    expect(FUNCTIONAL_ROUTE_PREFIXES).toContain('/brain');
  });
});
