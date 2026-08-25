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
  useTheme: () => ({ theme: 'light' }),
}));

describe('InlineWorkspaceDiff', () => {
  const dummyFile: FileEntry = {
    name: 'test_code.py',
    path: '/workspace/test_code.py',
    type: 'file',
    size: 120,
    mtime: '2026-08-22',
  };

  it('renders diff viewer with correct filename and diff view tag', () => {
    const handleClose = vi.fn();
    render(
      <InlineWorkspaceDiff
        file={dummyFile}
        workspace="/workspace"
        originalContent="def old_function():\n    pass\n"
        modifiedContent="def new_function():\n    return True\n"
        onClose={handleClose}
      />,
    );

    expect(screen.getByTestId('inline-workspace-diff')).toBeInTheDocument();
    expect(screen.getByText('test_code.py')).toBeInTheDocument();
    expect(screen.getByText('diffView')).toBeInTheDocument();
  });
});
