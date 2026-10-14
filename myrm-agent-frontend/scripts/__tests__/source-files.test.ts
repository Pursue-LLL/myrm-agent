// @vitest-environment node
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, relative } from 'node:path';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';

import { walkSourceFiles } from '../source-files.mjs';

let root: string;

const collect = (extensions: string[], options?: { includeTests?: boolean }) =>
  [...walkSourceFiles(root, new Set(extensions), options)].map((file) => relative(root, file)).sort();

beforeAll(() => {
  root = mkdtempSync(join(tmpdir(), 'source-files-'));
  const files = [
    'a.tsx',
    'util.ts',
    'style.css',
    'nested/b.tsx',
    'nested/c.test.tsx',
    '__tests__/d.tsx',
    'node_modules/pkg/e.tsx',
    '.next/f.tsx',
    'dist/g.tsx',
  ];
  for (const file of files) {
    mkdirSync(join(root, file, '..'), { recursive: true });
    writeFileSync(join(root, file), '');
  }
});

afterAll(() => {
  rmSync(root, { recursive: true, force: true });
});

describe('walkSourceFiles', () => {
  it('returns only matching extensions and excludes test files by default', () => {
    expect(collect(['.tsx'])).toEqual(['a.tsx', 'nested/b.tsx']);
    expect(collect(['.ts', '.tsx'])).toEqual(['a.tsx', 'nested/b.tsx', 'util.ts']);
  });

  it('includes test files when includeTests is set', () => {
    expect(collect(['.tsx'], { includeTests: true })).toEqual([
      '__tests__/d.tsx',
      'a.tsx',
      'nested/b.tsx',
      'nested/c.test.tsx',
    ]);
  });

  it('never descends into dependency or build output directories', () => {
    const all = collect(['.tsx'], { includeTests: true });
    expect(all.some((file) => /node_modules|\.next|dist/.test(file))).toBe(false);
  });
});
