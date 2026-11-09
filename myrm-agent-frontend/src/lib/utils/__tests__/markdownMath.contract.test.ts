/**
 * [INPUT] Every non-test .ts / .tsx source under src.
 * [OUTPUT] Vitest: formulas have one implementation, and every surface that renders them uses it the same way.
 * [POS] Guard against a new surface wiring its own math plugins: the parser policy, the percent escape and the
 * pre-pass only help where all three are in place, and the plugin order lives in `markdownMath.ts` alone.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

const SRC_ROOT = join(process.cwd(), 'src');
const MATH_MODULE = join('lib', 'utils', 'markdownMath.ts');
const MATH_PACKAGES = ['remark-math', 'micromark-extension-math', 'mdast-util-math', 'rehype-katex'];

const sources = readdirSync(SRC_ROOT, { recursive: true, encoding: 'utf8' })
  .filter((file) => /\.tsx?$/.test(file) && !file.includes('__tests__') && !file.includes('.test.'))
  .filter((file) => file !== MATH_MODULE)
  .map((file) => ({ path: join('src', file), text: readFileSync(join(SRC_ROOT, file), 'utf8') }));

const importsMathPackage = (text: string): boolean =>
  MATH_PACKAGES.some((name) => new RegExp(`['"]${name}['"]`).test(text));
const surfaces = sources.filter(({ text }) => /\b(mathPlugins|chatMathPlugins)\b/.test(text));

describe('markdown math pipeline contracts', () => {
  it('finds the known surfaces, so the scan cannot silently go empty', () => {
    expect(surfaces.map(({ path }) => path).sort()).toEqual([
      join('src', 'components', 'features', 'artifacts', 'renderers', 'DocumentPreview.tsx'),
      join('src', 'components', 'features', 'chat-window', 'CompactedArchiveModal.tsx'),
      join('src', 'components', 'features', 'chat-window', 'CompactedSummaryView.tsx'),
      join('src', 'components', 'features', 'message-box', 'MarkdownContent.tsx'),
      join('src', 'lib', 'utils', 'chat-export', 'chatExportHtml.ts'),
    ]);
  });

  it('keeps the math packages behind markdownMath.ts', () => {
    expect(sources.filter(({ text }) => importsMathPackage(text)).map(({ path }) => path)).toEqual([]);
  });

  it.each(surfaces.map(({ path, text }) => [path, text]))('%s runs the text pre-pass before parsing', (_path, text) => {
    expect(text).toContain('normalizeMathDelimiters(');
  });
});
