import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import CodeBlock from '@/components/features/markdown-render-tools/CodeBlock';
import { EnhancedSyntaxHighlighter } from '@/components/features/message-box/progress-steps/renderers/EnhancedSyntaxHighlighter';
import { LineNumberedCode } from '@/components/features/workspace-browser/WorkspaceTextViews';
import { TooltipProvider } from '@/components/primitives/tooltip';
import { DiffViewer } from '@/lib/diff/DiffViewer';
import { MAX_HIGHLIGHT_LINE_CHARS } from '@/lib/syntax/prism';
import { SYNTAX_THEME_LIGHT } from '@/lib/syntax/theme';

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light', resolvedTheme: 'light' }),
}));

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
  useLocale: () => 'en',
}));

const SHELL = 'if [ -f "$f" ]; then echo ok; fi';
const SHELL_DIFF = [
  '--- a/run.sh',
  '+++ b/run.sh',
  '@@ -1,1 +1,1 @@',
  '-if [ -f "$a" ]; then echo ok; fi',
  '+if [ -f "$b" ]; then echo ok; fi',
].join('\n');

/** The colour the light palette gives a token of `type`, in the form the DOM reports it. */
function lightColor(type: string): string {
  const rule = SYNTAX_THEME_LIGHT.styles.find((entry) => entry.types.includes(type));
  const probe = document.createElement('span');
  probe.style.color = String(rule?.style.color);
  return probe.style.color;
}

function keywordIf(): HTMLElement {
  const [keyword] = screen.getAllByText('if');
  if (!keyword) {
    throw new Error('the `if` token was not rendered');
  }
  return keyword;
}

/** The first string token on the page: the colour that had to be replaced for contrast, so it shows the palette in use. */
function firstString(): HTMLElement {
  const string = document.querySelector<HTMLElement>('.string');
  if (!string) {
    throw new Error('no string token was rendered');
  }
  return string;
}

function expectPalette(): void {
  expect(keywordIf().style.color).toBe(lightColor('keyword'));
  expect(firstString().style.color).toBe(lightColor('string'));
}

describe('shell code is coloured wherever the product shows it', () => {
  it('in a chat code block', () => {
    render(
      <TooltipProvider>
        <CodeBlock language="bash" value={SHELL} />
      </TooltipProvider>,
    );
    expect(keywordIf().className).toContain('keyword');
    expectPalette();
  });

  it('in the progress step of a shell command', () => {
    render(<EnhancedSyntaxHighlighter code={SHELL} language="bash" />);
    expectPalette();
  });

  it('in a diff of a .sh file', () => {
    render(<DiffViewer diff={SHELL_DIFF} filePath="run.sh" embedded />);
    expectPalette();
  });

  it('in the read-only view of a .sh file', () => {
    render(<LineNumberedCode content={SHELL} language="bash" />);
    expectPalette();
  });
});

describe('line numbers', () => {
  const numbersIn = (): HTMLElement[] => screen.getAllByText('1');
  const expectSecondaryText = (): void => {
    numbersIn().forEach((number) => expect(number.className).toContain('text-muted-foreground'));
  };

  it('take the secondary text colour in a chat code block', () => {
    render(
      <TooltipProvider>
        <CodeBlock language="bash" value={SHELL} />
      </TooltipProvider>,
    );
    expectSecondaryText();
  });

  it('take the secondary text colour in the progress step of a shell command', () => {
    render(<EnhancedSyntaxHighlighter code={SHELL} language="bash" />);
    expectSecondaryText();
  });

  it('take the secondary text colour in a diff, whatever the kind of the line', () => {
    render(<DiffViewer diff={SHELL_DIFF} filePath="run.sh" embedded />);
    expect(numbersIn().length).toBeGreaterThan(1);
    expectSecondaryText();
  });
});

describe('text with a line too long to colour safely', () => {
  const LONG_LINE = `echo "${'a'.repeat(MAX_HIGHLIGHT_LINE_CHARS)}"`;
  const WITH_LONG_LINE = `${SHELL}\n${LONG_LINE}\n`;

  it('stays uncoloured in a chat code block', () => {
    const { container } = render(
      <TooltipProvider>
        <CodeBlock language="bash" value={WITH_LONG_LINE} />
      </TooltipProvider>,
    );
    expect(container.querySelector('.keyword')).toBeNull();
  });

  it('stays uncoloured in the progress step of a shell command', () => {
    const { container } = render(
      <EnhancedSyntaxHighlighter code={WITH_LONG_LINE} language="bash" maxCollapsedLines={9} />,
    );
    expect(container.querySelector('.keyword')).toBeNull();
  });

  it('stays uncoloured in the read-only view of a file', () => {
    const { container } = render(<LineNumberedCode content={WITH_LONG_LINE} language="bash" />);
    expect(container.querySelector('.keyword')).toBeNull();
  });

  it('leaves only that line of a diff uncoloured, since a diff is coloured line by line', () => {
    const { container } = render(<DiffViewer diff={`${SHELL_DIFF}\n+${LONG_LINE}`} filePath="run.sh" embedded />);
    expect(container.querySelector('.keyword')).not.toBeNull();
    const strings = [...container.querySelectorAll('.string')].map((token) => token.textContent?.length ?? 0);
    expect(Math.max(...strings)).toBeLessThan(MAX_HIGHLIGHT_LINE_CHARS);
  });
});

describe('a ```diff code block', () => {
  it('shades added, removed and hunk-header lines and leaves context lines alone', () => {
    const value = ['@@ -1,3 +1,3 @@', ' same', '-old', '+new'].join('\n');
    const { container } = render(
      <TooltipProvider>
        <CodeBlock language="diff" value={value} />
      </TooltipProvider>,
    );

    const row = (line: number): string => container.querySelector(`#code-line-${line}`)?.className ?? '';
    expect(row(1)).toContain('bg-blue-500/10');
    expect(row(2)).not.toMatch(/bg-(blue|green|red)-500/);
    expect(row(3)).toContain('bg-red-500/10');
    expect(row(4)).toContain('bg-green-500/10');
  });

  it('keeps removed code readable: no strike-through, and no underline on added code, since the row tint already marks them', () => {
    const { container } = render(
      <TooltipProvider>
        <CodeBlock language="diff" value={['-old', '+new'].join('\n')} />
      </TooltipProvider>,
    );

    const decorations = (line: number): string[] =>
      [...container.querySelectorAll(`#code-line-${line} span[style]`)].map((span) => span.getAttribute('style') ?? '');
    expect(decorations(1).length).toBeGreaterThan(0);
    expect(decorations(1).join(' ')).not.toContain('line-through');
    expect(decorations(2).join(' ')).not.toContain('underline');
  });
});
