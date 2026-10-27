import { render, screen } from '@testing-library/react';
import { readdirSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { themes } from 'prism-react-renderer';
import { describe, expect, it, vi } from 'vitest';

import { TooltipProvider } from '@/components/primitives/tooltip';
import CodeBlock from '@/components/features/markdown-render-tools/CodeBlock';
import { EnhancedSyntaxHighlighter } from '@/components/features/message-box/progress-steps/renderers/EnhancedSyntaxHighlighter';
import { DiffViewer } from '@/lib/diff/DiffViewer';

/** What next-themes reports when the user picked "follow the system" and the OS is dark. */
const mockThemes = vi.hoisted(() => ({
  current: { theme: 'system', resolvedTheme: 'dark' } as { theme: string; resolvedTheme: string },
}));

vi.mock('next-themes', () => ({
  useTheme: () => mockThemes.current,
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
  useLocale: () => 'en',
}));

const SNIPPET = 'const answer = 42;';
const DIFF = ['--- a/a.ts', '+++ b/a.ts', '@@ -1,1 +1,1 @@', '-const answer = 41;', '+const answer = 42;'].join('\n');

/** The colour a palette gives the `const` keyword, in the form the DOM reports it. */
function keywordColor(palette: typeof themes.oneDark): string {
  const rule = palette.styles.find((entry) => entry.types.includes('keyword'));
  const probe = document.createElement('span');
  probe.style.color = String(rule?.style.color);
  return probe.style.color;
}

function renderedKeywordColor(): string {
  const [keyword] = screen.getAllByText('const');
  if (!keyword) {
    throw new Error('the keyword token was not rendered');
  }
  return keyword.style.color;
}

const SURFACES: ReadonlyArray<readonly [string, () => React.ReactElement]> = [
  [
    'code block in the chat',
    () => (
      <TooltipProvider>
        <CodeBlock language="typescript" value={SNIPPET} />
      </TooltipProvider>
    ),
  ],
  ['diff viewer', () => <DiffViewer diff={DIFF} filePath="a.ts" embedded />],
  ['tool output highlighter', () => <EnhancedSyntaxHighlighter code={SNIPPET} language="typescript" />],
];

describe('syntax colours follow the theme the OS resolved to', () => {
  it.each(SURFACES)('%s uses the dark palette when the setting is "system" and the OS is dark', (_name, surface) => {
    mockThemes.current = { theme: 'system', resolvedTheme: 'dark' };
    render(surface());

    expect(renderedKeywordColor()).toBe(keywordColor(themes.oneDark));
    expect(renderedKeywordColor()).not.toBe(keywordColor(themes.oneLight));
  });

  it.each(SURFACES)('%s uses the light palette when the setting is "system" and the OS is light', (_name, surface) => {
    mockThemes.current = { theme: 'system', resolvedTheme: 'light' };
    render(surface());

    expect(renderedKeywordColor()).toBe(keywordColor(themes.oneLight));
  });
});

describe('source guard', () => {
  function sourceFiles(dir: string): string[] {
    return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
      const full = path.join(dir, entry.name);
      if (entry.isDirectory()) {
        return entry.name === '__tests__' || entry.name === 'node_modules' ? [] : sourceFiles(full);
      }
      return /\.tsx?$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name) ? [full] : [];
    });
  }

  it('no component reads only the raw theme setting, which is the literal "system" for follow-the-OS users', () => {
    const root = path.resolve(process.cwd(), 'src');
    const offenders = sourceFiles(root)
      .filter((file) => /const\s*\{\s*theme\s*\}\s*=\s*useTheme\(\)/.test(readFileSync(file, 'utf8')))
      .map((file) => path.relative(root, file));

    expect(offenders).toEqual([]);
  });
});
