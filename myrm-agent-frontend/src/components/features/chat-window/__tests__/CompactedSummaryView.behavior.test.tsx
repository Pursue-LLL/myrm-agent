import { act, fireEvent, render, screen, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { BranchForkResult, ContextBranchRecord } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import { deferred } from '@/test-utils/deferred';

import { CompactedSummaryView } from '../CompactedSummaryView';
import { archived, branch, kit } from './compactedSummaryKit';
import { seedChat, setUpSummaryTest } from './compactedSummarySetup';

vi.mock('next-intl', async () => (await import('./compactedSummaryKit')).nextIntlMock());
vi.mock('next/navigation', async () => (await import('./compactedSummaryKit')).navigationMock());
vi.mock('@/services/chat', async () => (await import('./compactedSummaryKit')).chatServiceMock());
vi.mock('@/services/i18nToastService', async () => (await import('./compactedSummaryKit')).toastServiceMock());

// The milestone cards, the anchor strip and the archive window have their own tests; these stand-ins expose
// exactly what the view hands them.
vi.mock('../../compaction-milestone', () => ({
  CompactedMilestoneCard: ({ entry }: { entry: { summary: string; archivedCount: number; savedTokens: number } }) => (
    <div data-testid="milestone" data-archived={entry.archivedCount} data-saved={entry.savedTokens}>
      {entry.summary}
    </div>
  ),
  BranchSummaryCard: ({
    entry,
  }: {
    entry: { sourceBranchName: string; summary: string; keyTakeaways: string[]; createdAt: string };
  }) => (
    <div data-testid="branch-card" data-created-at={entry.createdAt}>
      {[entry.sourceBranchName, entry.summary, ...entry.keyTakeaways].join('|')}
    </div>
  ),
}));
vi.mock('../../compaction-milestone/compactionParser', () => ({
  parseCompactionEntry: (summary: string, meta: { tokensSaved?: number } | null, archive: unknown[]) => ({
    summary,
    archivedCount: archive.length,
    savedTokens: meta?.tokensSaved ?? -1,
  }),
}));
vi.mock('../CompactionAnchorStrip', () => ({
  CompactionAnchorStrip: ({ anchors }: { anchors: { filePaths?: string[] } }) => (
    <div data-testid="anchors">{(anchors.filePaths ?? []).join(',')}</div>
  ),
}));
vi.mock('../CompactedArchiveModal', () => ({
  CompactedArchiveModal: (props: {
    isOpen: boolean;
    isLoading: boolean;
    messages: Array<{ id: string }>;
    title: string;
    onClose: () => void;
  }) =>
    props.isOpen ? (
      <div data-testid="archive-modal" data-loading={String(props.isLoading)}>
        {props.title}|{props.messages.map((message) => message.id).join(',')}
        <button type="button" onClick={props.onClose}>
          close-archive
        </button>
      </div>
    ) : null,
}));

setUpSummaryTest();

const chatState = () => useChatStore.getState();

async function click(element: HTMLElement): Promise<void> {
  await act(async () => {
    fireEvent.click(element);
  });
}

const button = (name: string) => screen.getByRole('button', { name });

describe('CompactedSummaryView summary', () => {
  it('renders nothing for a chat without a summary', () => {
    seedChat({ compactedSummary: null });

    const { container } = render(<CompactedSummaryView />);

    expect(container).toBeEmptyDOMElement();
  });

  it('shows the summary as formatted text under its title', () => {
    seedChat({ compactedSummary: 'Decided on **Postgres**.' });

    const { container } = render(<CompactedSummaryView />);

    expect(screen.getByText('title')).toBeInTheDocument();
    expect(container.querySelector('.prose strong')?.textContent).toBe('Postgres');
  });

  it('opens web links in a new tab without handing over the opener, and keeps site links in place', () => {
    seedChat({ compactedSummary: '[docs](https://example.com/docs) and [home](/home)' });

    render(<CompactedSummaryView />);

    const external = screen.getByRole('link', { name: 'docs' });
    expect(external).toHaveAttribute('target', '_blank');
    expect(external).toHaveAttribute('rel', 'noopener noreferrer');
    const internal = screen.getByRole('link', { name: 'home' });
    expect(internal).toHaveAttribute('href', '/home');
    expect(internal).not.toHaveAttribute('target');
  });

  it('hands the milestone card the summary text without the anchor block, and the anchor strip the anchors', () => {
    seedChat({
      compactedSummary: 'Body text\n<!-- EXACT_ANCHOR_JSON: {"file_paths":["src/a.ts"]} -->',
    });

    render(<CompactedSummaryView />);

    expect(screen.getByTestId('milestone').textContent).toBe('Body text');
    expect(screen.getByTestId('anchors').textContent).toBe('src/a.ts');
  });

  it('hands the anchor strip the anchors compaction recorded as data, and the milestone card its figures', () => {
    seedChat({ lastCompactionMeta: { tokensSaved: 1200, exactAnchors: { filePaths: ['src/recorded.ts'] } } });

    render(<CompactedSummaryView />);

    expect(screen.getByTestId('anchors').textContent).toBe('src/recorded.ts');
    expect(screen.getByTestId('milestone')).toHaveAttribute('data-saved', '1200');
  });

  it.each([
    [1200, '1.2K'],
    [1000, '1.0K'],
    [999, '999'],
  ])('reports %i saved tokens as %s', (tokensSaved, shown) => {
    seedChat({ lastCompactionMeta: { tokensSaved } });

    render(<CompactedSummaryView />);

    expect(screen.getByText(`tokensSaved {"tokens":"${shown}"}`)).toBeInTheDocument();
  });

  it('leaves the savings line, and the save-snapshot button with it, out when nothing was saved', () => {
    seedChat({ lastCompactionMeta: { tokensSaved: 0, snapshotPath: '/snapshots/latest.json' } });

    render(<CompactedSummaryView />);

    expect(screen.queryByText(/tokensSaved/)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'saveBookmark' })).not.toBeInTheDocument();
  });

  it('offers no save-snapshot button when compaction left no snapshot file', () => {
    seedChat({ lastCompactionMeta: { tokensSaved: 1200 } });

    render(<CompactedSummaryView />);

    expect(screen.getByText(/tokensSaved/)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'saveBookmark' })).not.toBeInTheDocument();
  });
});

describe('CompactedSummaryView editing', () => {
  it('edits in a text box holding the current summary, and hides the anchor strip meanwhile', async () => {
    seedChat({ compactedSummary: 'Body\n<!-- EXACT_ANCHOR_JSON: {"file_paths":["src/a.ts"]} -->' });
    render(<CompactedSummaryView />);

    await click(button('edit'));

    expect(screen.getByRole('textbox')).toHaveValue('Body\n<!-- EXACT_ANCHOR_JSON: {"file_paths":["src/a.ts"]} -->');
    expect(screen.queryByTestId('anchors')).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'edit' })).not.toBeInTheDocument();
  });

  it('saves the edit and shows the new text', async () => {
    kit.updateCompactionSummary.mockResolvedValue(undefined);
    render(<CompactedSummaryView />);
    await click(button('edit'));

    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Rewritten summary' } });
    await click(button('save'));

    expect(kit.updateCompactionSummary).toHaveBeenCalledExactlyOnceWith('chat-1', 'Rewritten summary');
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(screen.getAllByText('Rewritten summary').length).toBeGreaterThan(0);
    expect(chatState().compactedSummary).toBe('Rewritten summary');
  });

  it('throws the edit away on cancel', async () => {
    render(<CompactedSummaryView />);
    await click(button('edit'));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Never saved' } });

    await click(button('cancel'));

    expect(kit.updateCompactionSummary).not.toHaveBeenCalled();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    expect(chatState().compactedSummary).toBe('The summary');
  });

  it('starts the next edit from the saved text, not from the abandoned one', async () => {
    render(<CompactedSummaryView />);
    await click(button('edit'));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Abandoned' } });
    await click(button('cancel'));

    await click(button('edit'));

    expect(screen.getByRole('textbox')).toHaveValue('The summary');
  });

  it('blocks both buttons while the save runs', async () => {
    const pending = deferred<void>();
    kit.updateCompactionSummary.mockReturnValue(pending.promise);
    render(<CompactedSummaryView />);
    await click(button('edit'));

    await click(button('save'));

    expect(button('save')).toBeDisabled();
    expect(button('cancel')).toBeDisabled();
    await act(async () => pending.resolve());
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('keeps the edit on screen when saving fails', async () => {
    kit.updateCompactionSummary.mockRejectedValue(new Error('offline'));
    render(<CompactedSummaryView />);
    await click(button('edit'));
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Unsaved work' } });

    await click(button('save'));

    expect(screen.getByRole('textbox')).toHaveValue('Unsaved work');
    expect(button('save')).toBeEnabled();
    expect(kit.showI18nToast).toHaveBeenCalledExactlyOnceWith('chat.compactedSummary.summarySaveFailed', undefined, {
      type: 'error',
    });
  });
});

describe('CompactedSummaryView archive', () => {
  it('opens the archive window, loads the archived messages into it and into the milestone card', async () => {
    const pending = deferred<{ messages: ReturnType<typeof archived>[] }>();
    kit.getChatArchive.mockReturnValue(pending.promise);
    render(<CompactedSummaryView />);
    expect(screen.queryByTestId('archive-modal')).not.toBeInTheDocument();

    await click(button('foldLabel'));
    expect(screen.getByTestId('archive-modal')).toHaveAttribute('data-loading', 'true');
    await act(async () => pending.resolve({ messages: [archived('m1'), archived('m2')] }));

    const modal = screen.getByTestId('archive-modal');
    expect(modal).toHaveAttribute('data-loading', 'false');
    expect(modal.textContent).toContain('archiveTitle|m1,m2');
    expect(screen.getByTestId('milestone')).toHaveAttribute('data-archived', '2');
  });

  it('closes the archive window from the window itself', async () => {
    kit.getChatArchive.mockResolvedValue({ messages: [archived('m1')] });
    render(<CompactedSummaryView />);
    await click(button('foldLabel'));

    await click(within(screen.getByTestId('archive-modal')).getByRole('button', { name: 'close-archive' }));

    expect(screen.queryByTestId('archive-modal')).not.toBeInTheDocument();
  });

  it('does not leave an empty window open when the archive cannot be loaded', async () => {
    kit.getChatArchive.mockRejectedValue(new Error('offline'));
    render(<CompactedSummaryView />);

    await click(button('foldLabel'));

    expect(screen.queryByTestId('archive-modal')).not.toBeInTheDocument();
    expect(kit.showI18nToast).toHaveBeenCalledExactlyOnceWith('chat.compactedSummary.archiveLoadFailed', undefined, {
      type: 'error',
    });
  });
});

describe('CompactedSummaryView snapshots', () => {
  const list = () => screen.getByTestId('compacted-summary-bookmarks');

  it('says there are no snapshots, and shows no branch card, until one is saved', () => {
    render(<CompactedSummaryView />);

    expect(list()).toHaveAttribute('data-bookmarks-state', 'empty');
    expect(screen.getByText('bookmarksEmpty')).toBeInTheDocument();
    expect(screen.queryByTestId('branch-card')).not.toBeInTheDocument();
  });

  it('lists the snapshots newest first and describes the newest one in the branch card', () => {
    seedChat({
      contextBranches: [
        branch('b1', 'Oldest', '/s/b1.json', '2026-01-01T09:00:00'),
        branch('b2', '', '/s/b2.json', '2026-02-02T10:30:00'),
      ],
    });

    render(<CompactedSummaryView />);

    const items = screen.getAllByTestId('compacted-summary-bookmark-item');
    expect(items.map((item) => item.getAttribute('title'))).toEqual(['/s/b2.json', '/s/b1.json']);
    expect(items[0]?.textContent).toContain('b2.json');
    expect(items[0]?.textContent).toContain('2026-02-02 10:30');
    expect(items[1]?.textContent).toContain('Oldest');
    expect(screen.getByTestId('branch-card').textContent).toBe(
      'b2.json|branchContextDistilled|branchSnapshotArchived {"path":"/s/b2.json"}',
    );
    expect(screen.getByTestId('branch-card')).toHaveAttribute('data-created-at', '2026-02-02T10:30:00');
  });

  it('leaves the time out for a snapshot whose date is unreadable', () => {
    seedChat({ contextBranches: [branch('b1', 'Named', '/s/b1.json', 'not a date')] });

    render(<CompactedSummaryView />);

    expect(screen.getByTestId('compacted-summary-bookmark-item').textContent).toBe('NamedbookmarkFork');
  });

  it('saves the latest snapshot, shows that it is saving, then lists it', async () => {
    const pending = deferred<ContextBranchRecord>();
    kit.createContextBranch.mockReturnValue(pending.promise);
    kit.listContextBranches.mockResolvedValue([branch('b1', 'Fresh')]);
    render(<CompactedSummaryView />);

    await click(button('saveBookmark'));
    expect(button('savingBookmark')).toBeDisabled();
    await act(async () => pending.resolve(branch('b1', 'Fresh')));

    expect(kit.createContextBranch).toHaveBeenCalledExactlyOnceWith('chat-1', {
      snapshot_path: '/snapshots/latest.json',
    });
    expect(button('saveBookmark')).toBeEnabled();
    expect(screen.getByTestId('compacted-summary-bookmark-item').textContent).toContain('Fresh');
    expect(kit.showI18nToast).toHaveBeenCalledExactlyOnceWith('chat.compactedSummary.bookmarkSaved', undefined, {
      type: 'success',
    });
  });

  it('retries a failed listing from the error row', async () => {
    seedChat({ contextBranchesLoadError: 'load_failed' });
    kit.listContextBranches.mockResolvedValue([branch('b1', 'Recovered')]);
    render(<CompactedSummaryView />);
    expect(list()).toHaveAttribute('data-bookmarks-state', 'error');

    await click(button('bookmarksRetry'));

    expect(kit.listContextBranches).toHaveBeenCalledExactlyOnceWith('chat-1');
    expect(list()).toHaveAttribute('data-bookmarks-state', 'ready');
    expect(screen.getByTestId('compacted-summary-bookmark-item').textContent).toContain('Recovered');
  });

  it('shows that snapshots are loading while a retry runs', async () => {
    seedChat({ contextBranchesLoadError: 'load_failed' });
    const pending = deferred<ContextBranchRecord[]>();
    kit.listContextBranches.mockReturnValue(pending.promise);
    render(<CompactedSummaryView />);

    await click(button('bookmarksRetry'));
    expect(list()).toHaveAttribute('data-bookmarks-state', 'loading');
    await act(async () => pending.resolve([]));

    expect(list()).toHaveAttribute('data-bookmarks-state', 'empty');
  });

  describe('opening one in a new chat', () => {
    beforeEach(() => {
      seedChat({ contextBranches: [branch('b1', 'First'), branch('b2', 'Second')] });
    });

    const forkButton = (branchId: string) =>
      screen
        .getAllByTestId('compacted-summary-bookmark-fork')
        .find((element) => element.getAttribute('data-branch-id') === branchId) as HTMLButtonElement;

    it('forks the snapshot that was clicked, not another one', async () => {
      kit.forkContextBranch.mockResolvedValue({ new_chat_id: 'chat-9' } as BranchForkResult);
      render(<CompactedSummaryView />);

      await click(forkButton('b1'));

      expect(kit.forkContextBranch).toHaveBeenCalledExactlyOnceWith('chat-1', 'b1', 'First');
      expect(kit.push).toHaveBeenCalledExactlyOnceWith('/chat-9');
    });

    it('marks the snapshot that is opening and ignores a second click on it', async () => {
      const pending = deferred<BranchForkResult>();
      kit.forkContextBranch.mockReturnValue(pending.promise);
      render(<CompactedSummaryView />);

      await click(forkButton('b1'));
      expect(forkButton('b1')).toBeDisabled();
      expect(forkButton('b1').textContent).toBe('bookmarkForking');
      expect(forkButton('b2').textContent).toBe('bookmarkFork');
      await click(forkButton('b1'));
      await click(forkButton('b2'));
      expect(kit.forkContextBranch).toHaveBeenCalledTimes(1);

      await act(async () => pending.resolve({ new_chat_id: 'chat-9' } as BranchForkResult));
      expect(forkButton('b1')).toBeEnabled();
    });

    it('does not fork anything for a click outside a fork button', async () => {
      render(<CompactedSummaryView />);

      await click(screen.getAllByTestId('compacted-summary-bookmark-item')[0] as HTMLElement);
      await click(screen.getByText('title'));

      expect(kit.forkContextBranch).not.toHaveBeenCalled();
    });
  });
});
