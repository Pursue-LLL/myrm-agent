/**
 * Monaco 只能经 `lazy-monaco-editor.tsx` 进入应用：绕开它的编辑器拿不到统一的明暗主题（Monaco 的主题是整页共享的，
 * 它挂载时传的主题会改写页面上所有编辑器），也不会先把随包的 Monaco 登记给 loader（离线时会一直停在 Loading）。
 * 只引用类型（`import type`）不受限制。
 */
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC_ROOT = path.resolve(process.cwd(), 'src');

/** The wrapper itself, and the hover preloader that warms the same bundled Monaco. */
const ENTRY_POINTS = new Set([
  'components/features/app-shell/lazy-monaco-editor.tsx',
  'lib/utils/componentPreloader.ts',
]);

const VALUE_IMPORT = /^import\s+(?!type\b)[^;]*?from\s+['"]@monaco-editor\/react['"]/m;
const DYNAMIC_IMPORT = /import\(\s*['"]@monaco-editor\/react['"]\s*\)/;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      return entry.name === '__tests__' || entry.name === 'node_modules' ? [] : sourceFiles(full);
    }
    return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [full] : [];
  });
}

describe('Monaco entry point', () => {
  it('is the only place that loads @monaco-editor/react as a value', () => {
    const offenders = sourceFiles(SRC_ROOT)
      .map((file) => path.relative(SRC_ROOT, file).split(path.sep).join('/'))
      .filter((relative) => !ENTRY_POINTS.has(relative))
      .filter((relative) => {
        const source = readFileSync(path.join(SRC_ROOT, relative), 'utf8');
        return VALUE_IMPORT.test(source) || DYNAMIC_IMPORT.test(source);
      });

    expect(offenders).toEqual([]);
  });

  it('still finds the entry points it exempts', () => {
    for (const relative of ENTRY_POINTS) {
      const source = readFileSync(path.join(SRC_ROOT, relative), 'utf8');
      expect(DYNAMIC_IMPORT.test(source)).toBe(true);
    }
  });
});
