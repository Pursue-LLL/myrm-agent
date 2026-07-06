import { describe, expect, test } from 'bun:test';

import { assertFractalDocsCompliant, collectFractalDocViolations } from './check-fractal-docs';

describe('check-fractal-docs', () => {
  test('required _ARCH paths and core IOP headers are present', () => {
    expect(collectFractalDocViolations()).toEqual([]);
    expect(() => assertFractalDocsCompliant()).not.toThrow();
  });
});
