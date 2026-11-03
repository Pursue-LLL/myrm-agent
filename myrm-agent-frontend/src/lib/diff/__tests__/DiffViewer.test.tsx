import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { DiffViewer } from '../DiffViewer';

vi.mock('next-themes', () => ({
  useTheme: () => ({ theme: 'light', resolvedTheme: 'light' }),
}));

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

const TEXT_DIFF = ['--- a/demo.txt', '+++ b/demo.txt', '@@ -1 +1 @@', '-alpha', '+beta'].join('\n');

describe('DiffViewer', () => {
  it('labels the toolbar buttons through translations and switches the view label with the mode', () => {
    render(<DiffViewer diff={TEXT_DIFF} filePath="demo.txt" onClose={vi.fn()} />);

    expect(screen.getByTitle('copyDiff')).toBeInTheDocument();
    expect(screen.getByTitle('close')).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('splitView'));
    expect(screen.getByTitle('unifiedView')).toBeInTheDocument();
  });

  it('falls back to a translated name when no file path is known', () => {
    render(<DiffViewer diff={['@@ -1 +1 @@', '-alpha', '+beta'].join('\n')} />);

    expect(screen.getByTitle('unknownFile')).toBeInTheDocument();
  });

  it('announces a binary change through a translation', () => {
    render(<DiffViewer diff="Binary files a/logo.png and b/logo.png differ" filePath="logo.png" />);

    expect(screen.getByText('binaryChanged')).toBeInTheDocument();
  });

  it('announces an empty diff through a translation', () => {
    render(<DiffViewer diff="" filePath="demo.txt" />);

    expect(screen.getByText('noChanges')).toBeInTheDocument();
  });
});
