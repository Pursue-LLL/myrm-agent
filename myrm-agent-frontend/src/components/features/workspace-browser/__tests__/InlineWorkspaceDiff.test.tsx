// @vitest-environment jsdom
import '@testing-library/jest-dom/vitest';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { InlineWorkspaceDiff } from '../InlineWorkspaceDiff';
import type { FileEntry } from '@/services/chat';

const stableT = (key: string) => key;

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light', resolvedTheme: 'light' }),
}));

const textFile: FileEntry = {
  name: 'notes.txt',
  path: '/workspace/notes.txt',
  type: 'file',
  is_text: true,
  children: [],
  size: 120,
  mtime: '2026-08-22',
};

const numberedLines = (count: number) => Array.from({ length: count }, (_, index) => `line ${index + 1}`);

describe('InlineWorkspaceDiff', () => {
  it('renders diff viewer with correct filename and diff view tag', () => {
    render(
      <InlineWorkspaceDiff
        file={{ ...textFile, name: 'test_code.py', path: '/workspace/test_code.py' }}
        originalContent="def old_function():\n    pass\n"
        modifiedContent="def new_function():\n    return True\n"
        onClose={vi.fn()}
      />,
    );

    expect(screen.getByTestId('inline-workspace-diff')).toBeInTheDocument();
    expect(screen.getByText('test_code.py')).toBeInTheDocument();
    expect(screen.getByText('diffView')).toBeInTheDocument();
  });

  it('shows one inserted line as the only change, not every line below it as removed and added', () => {
    const before = numberedLines(60);
    const after = [...before.slice(0, 30), 'inserted line', ...before.slice(30)];

    render(
      <InlineWorkspaceDiff
        file={textFile}
        originalContent={`${before.join('\n')}\n`}
        modifiedContent={`${after.join('\n')}\n`}
        onClose={vi.fn()}
      />,
    );

    expect(screen.getAllByText('inserted line')).toHaveLength(1);
    expect(screen.queryAllByText('+')).toHaveLength(1);
    expect(screen.queryAllByText('-')).toHaveLength(0);
    // Lines far from the edit are not part of the change, so they are not listed at all.
    expect(screen.queryAllByText('line 45')).toHaveLength(0);
  });

  it('lets the panel scroll the diff instead of boxing it into a short scroll area of its own', () => {
    const { container } = render(
      <InlineWorkspaceDiff file={textFile} originalContent="a\n" modifiedContent="b\n" onClose={vi.fn()} />,
    );

    expect(container.querySelector('[style*="max-height"]')).toHaveStyle({ maxHeight: 'none' });
  });
});
