/** @vitest-environment jsdom */
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

const summary = vi.hoisted(() => ({ text: '' }));
const stableT = (key: string) => key;

vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('../useCompactedSummaryState', () => ({
  bookmarkDisplayLabel: () => '',
  useCompactedSummaryState: () => ({
    compactedSummary: summary.text,
    lastCompactionMeta: null,
    contextBranchesLoadError: null,
    bookmarks: [],
    bookmarksLoading: false,
    forkingBranchId: null,
    isEditing: false,
    editValue: '',
    setEditValue: vi.fn(),
    isSaving: false,
    isSavingBookmark: false,
    isArchiveOpen: false,
    setIsArchiveOpen: vi.fn(),
    archiveMessages: [],
    isLoadingArchive: false,
    handleEdit: vi.fn(),
    handleCancel: vi.fn(),
    handleSave: vi.fn(),
    handleViewArchive: vi.fn(),
    handleSaveBookmark: vi.fn(),
    handleForkFromBookmark: vi.fn(),
    loadBookmarks: vi.fn(),
  }),
}));
vi.mock('../../compaction-milestone', () => ({ CompactedMilestoneCard: () => null, BranchSummaryCard: () => null }));
vi.mock('../../compaction-milestone/compactionParser', () => ({ parseCompactionEntry: () => ({}) }));
vi.mock('../CompactedBookmarksList', () => ({ CompactedBookmarksList: () => null }));

import { CompactedSummaryView } from '../CompactedSummaryView';

function renderSummary(text: string): HTMLElement {
  summary.text = text;
  return render(<CompactedSummaryView />).container;
}

describe('CompactedSummaryView math', () => {
  it('renders formulas in any notation and leaves prices as text', () => {
    const container = renderSummary(
      'Budget: $5 per seat and $10 per month.\n\nArea \\(\\pi r^2\\) and $$e^{i\\pi}=-1$$',
    );

    expect(container.querySelectorAll('.katex')).toHaveLength(2);
    expect(container.textContent).toContain('Budget: $5 per seat and $10 per month.');
  });

  it('does not turn commands that link or load a resource into links or images', () => {
    const container = renderSummary('$\\href{https://example.com}{x}$ $\\includegraphics{https://example.com/a.png}$');

    expect(container.querySelectorAll('.katex')).toHaveLength(2);
    expect(container.querySelectorAll('.prose a, .prose img')).toHaveLength(0);
  });
});
