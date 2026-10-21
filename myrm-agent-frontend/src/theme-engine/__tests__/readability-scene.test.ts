import { describe, expect, it } from 'vitest';
import { FUNCTIONAL_ROUTE_PREFIXES, IMMERSIVE_EXACT_PATHS, resolveReadabilityScene } from '../readability-scene';

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

  it('normalizes trailing slashes', () => {
    expect(resolveReadabilityScene('/kanban/')).toBe('functional');
    expect(resolveReadabilityScene('/chat/')).toBe('immersive');
  });

  it('exports functional prefixes used by preinit script', () => {
    expect(FUNCTIONAL_ROUTE_PREFIXES.length).toBeGreaterThan(10);
    expect(FUNCTIONAL_ROUTE_PREFIXES).toContain('/brain');
  });
});
