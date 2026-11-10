import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { ContextBranchRecord } from '@/services/chat';

import { CompactedBookmarksList, type CompactedBookmarksListProps } from '../CompactedBookmarksList';
import { branch } from './compactedSummaryKit';

const labels: CompactedBookmarksListProps['labels'] = {
  bookmarksTitle: 'Snapshots',
  bookmarksLoading: 'Loading snapshots',
  bookmarksLoadError: 'Could not load snapshots',
  bookmarksRetry: 'Retry',
  bookmarksEmpty: 'No snapshots yet',
  bookmarkForking: 'Opening',
  bookmarkFork: 'Open in new chat',
};

const baseProps: CompactedBookmarksListProps = {
  bookmarks: [],
  bookmarksLoading: false,
  contextBranchesLoadError: null,
  forkingBranchId: null,
  onRetryLoad: vi.fn(),
  formatBookmarkTime: (iso) => (iso ? `at ${iso}` : ''),
  bookmarkDisplayLabel: (record: ContextBranchRecord) => record.label || 'unnamed',
  labels,
};

function renderList(overrides: Partial<CompactedBookmarksListProps> = {}): HTMLElement {
  render(<CompactedBookmarksList {...baseProps} {...overrides} />);
  return screen.getByTestId('compacted-summary-bookmarks');
}

describe('CompactedBookmarksList', () => {
  it('says it is loading, and nothing else', () => {
    const root = renderList({ bookmarksLoading: true, bookmarks: [branch('a')] });

    expect(root).toHaveAttribute('data-bookmarks-state', 'loading');
    expect(screen.getByText('Loading snapshots')).toBeInTheDocument();
    expect(screen.queryByTestId('compacted-summary-bookmark-item')).not.toBeInTheDocument();
  });

  it('offers a retry when loading failed, and that retry asks the parent to reload', () => {
    const onRetryLoad = vi.fn();
    const root = renderList({ contextBranchesLoadError: 'load_failed', bookmarks: [branch('a')], onRetryLoad });

    expect(root).toHaveAttribute('data-bookmarks-state', 'error');
    expect(screen.getByText('Could not load snapshots')).toBeInTheDocument();
    expect(screen.queryByTestId('compacted-summary-bookmark-item')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    expect(onRetryLoad).toHaveBeenCalledTimes(1);
  });

  it('shows loading rather than the error while a retry is running', () => {
    const root = renderList({ bookmarksLoading: true, contextBranchesLoadError: 'load_failed' });

    expect(root).toHaveAttribute('data-bookmarks-state', 'loading');
    expect(screen.queryByText('Could not load snapshots')).not.toBeInTheDocument();
  });

  it('says there are no snapshots yet', () => {
    const root = renderList();

    expect(root).toHaveAttribute('data-bookmarks-state', 'empty');
    expect(screen.getByText('No snapshots yet')).toBeInTheDocument();
  });

  it('lists each snapshot with its name, time and file, in the order given', () => {
    const root = renderList({
      bookmarks: [
        branch('b2', 'Newer', '/s/b2.json', '2026-02-02T10:00:00'),
        branch('b1', '', '/s/b1.json', '2026-01-01T09:00:00'),
      ],
    });

    expect(root).toHaveAttribute('data-bookmarks-state', 'ready');
    const items = screen.getAllByTestId('compacted-summary-bookmark-item');
    expect(items.map((item) => item.textContent)).toEqual([
      'Newerat 2026-02-02T10:00:00Open in new chat',
      'unnamedat 2026-01-01T09:00:00Open in new chat',
    ]);
    expect(items.map((item) => item.getAttribute('title'))).toEqual(['/s/b2.json', '/s/b1.json']);
  });

  it('leaves the time out when it cannot be formatted', () => {
    renderList({ bookmarks: [branch('b1', 'Named', '/s/b1.json', '')], formatBookmarkTime: () => '' });

    expect(screen.getByTestId('compacted-summary-bookmark-item').textContent).toBe('NamedOpen in new chat');
  });

  it('tags each fork button with its snapshot and shows which one is opening', () => {
    renderList({ bookmarks: [branch('b2', 'Two'), branch('b1', 'One')], forkingBranchId: 'b1' });

    const buttons = screen.getAllByTestId('compacted-summary-bookmark-fork');
    expect(buttons.map((button) => button.getAttribute('data-branch-id'))).toEqual(['b2', 'b1']);
    expect(buttons.map((button) => button.textContent)).toEqual(['Open in new chat', 'Opening']);
    expect(buttons.map((button) => (button as HTMLButtonElement).disabled)).toEqual([false, true]);
  });
});
