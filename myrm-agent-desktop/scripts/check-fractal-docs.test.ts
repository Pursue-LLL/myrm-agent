import { describe, expect, test } from 'bun:test';

import {
  assertFractalDocsCompliant,
  collectFractalDocViolations,
  collectRecursiveArchGaps,
  discoverArchPathsUnderScanRoots,
  getRequiredArchPaths,
} from './check-fractal-docs';

describe('check-fractal-docs', () => {
  test('required _ARCH paths, recursive scan, and core IOP headers are present', () => {
    expect(collectRecursiveArchGaps()).toEqual([]);
    expect(collectFractalDocViolations()).toEqual([]);
    expect(() => assertFractalDocsCompliant()).not.toThrow();
  });

  test('discovered arch paths include new submodules without manual list drift', () => {
    const required = getRequiredArchPaths();
    expect(required).toContain('src-tauri/src/commands/agent/_ARCH.md');
    expect(required).toContain('sidecar/agent-runner/src/_ARCH.md');
    expect(discoverArchPathsUnderScanRoots().length).toBeGreaterThanOrEqual(10);
  });
});
