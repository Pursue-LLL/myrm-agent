import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { SessionTouchedFilesPopover } from '../SessionTouchedFilesPopover';
import type { SessionTouchedFile } from '../worktreeTypes';

const mockTranslations = (key: string) => {
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => mockTranslations,
}));

beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn(function mockShowModal(this: HTMLDialogElement) {
    this.open = true;
  });
  HTMLDialogElement.prototype.close = vi.fn(function mockClose(this: HTMLDialogElement) {
    this.open = false;
  });
});

describe('SessionTouchedFilesPopover', () => {
  const dummyTouchedFiles: SessionTouchedFile[] = [
    { file_path: 'src/components/Button.tsx', change_type: 'modified', touched_at: '2026-09-02T10:00:00Z' },
    { file_path: 'src/hooks/useToggle.ts', change_type: 'created', touched_at: '2026-09-02T10:05:00Z' },
    { file_path: 'src/legacy/OldView.tsx', change_type: 'deleted', touched_at: '2026-09-02T10:10:00Z' },
  ];

  it('renders touched file list and counts', () => {
    const closeMock = vi.fn();
    render(<SessionTouchedFilesPopover touchedFiles={dummyTouchedFiles} onClose={closeMock} />);

    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('src/components/Button.tsx')).toBeInTheDocument();
    expect(screen.getByText('src/hooks/useToggle.ts')).toBeInTheDocument();
    expect(screen.getByText('src/legacy/OldView.tsx')).toBeInTheDocument();
  });

  it('filters touched files by keyword input', () => {
    const closeMock = vi.fn();
    render(<SessionTouchedFilesPopover touchedFiles={dummyTouchedFiles} onClose={closeMock} />);

    const searchInput = screen.getByPlaceholderText(/searchFilesPlaceholder/i);
    fireEvent.change(searchInput, { target: { value: 'Toggle' } });

    expect(screen.getByText('src/hooks/useToggle.ts')).toBeInTheDocument();
    expect(screen.queryByText('src/components/Button.tsx')).not.toBeInTheDocument();
  });

  it('filters touched files by change type dropdown', () => {
    const closeMock = vi.fn();
    render(<SessionTouchedFilesPopover touchedFiles={dummyTouchedFiles} onClose={closeMock} />);

    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'created' } });

    expect(screen.getByText('src/hooks/useToggle.ts')).toBeInTheDocument();
    expect(screen.queryByText('src/components/Button.tsx')).not.toBeInTheDocument();
    expect(screen.queryByText('src/legacy/OldView.tsx')).not.toBeInTheDocument();
  });

  it('invokes onSelectFile and onClose callbacks', () => {
    const closeMock = vi.fn();
    const selectMock = vi.fn();
    render(
      <SessionTouchedFilesPopover
        touchedFiles={dummyTouchedFiles}
        onClose={closeMock}
        onSelectFile={selectMock}
      />,
    );

    const fileBtn = screen.getByText('src/components/Button.tsx');
    fireEvent.click(fileBtn);
    expect(selectMock).toHaveBeenCalledWith('src/components/Button.tsx');

    const closeBtn = screen.getByRole('button', { name: /close/i });
    fireEvent.click(closeBtn);
    expect(closeMock).toHaveBeenCalledTimes(1);
  });
});
