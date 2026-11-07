import { screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { deferred } from '@/test-utils/deferred';
import { settle } from '@/test-utils/fakeClock';
import {
  attr,
  button,
  byTitle,
  click,
  openTab,
  patchStore,
  renderSection,
  resetKit,
  storeActions,
  toast,
  world,
} from './memorySectionTestKit';
import { memoryOf, pageOf } from './memorySectionFixtures';

const openTrashTab = async () => {
  renderSection();
  await openTab('trash');
  storeActions.fetchArchivedMemories.mockClear();
};

beforeEach(resetKit);

describe('MemorySection trash tab', () => {
  it('hands the archived memories and their loading state to the panel', async () => {
    await patchStore({
      archivedMemories: [memoryOf('a1'), memoryOf('a2')],
      archivedLoading: true,
      archivedPagination: pageOf(1, true, 30),
    });
    renderSection();
    await openTab('trash');

    expect(attr('trash-panel', 'data-count')).toBe('2');
    expect(attr('trash-panel', 'data-loading')).toBe('true');
    expect(attr('trash-panel', 'data-next')).toBe('true');
  });

  it('restores a memory and confirms it', async () => {
    await openTrashTab();

    await click(button('trash:restore'));

    expect(storeActions.restoreMemory).toHaveBeenCalledExactlyOnceWith('trashed-1');
    expect(toast).toHaveBeenCalledExactlyOnceWith({ title: 'trash.restoreSuccess' });
  });

  it('reports a restore that failed', async () => {
    storeActions.restoreMemory.mockRejectedValue(new Error('missing'));
    await openTrashTab();

    await click(button('trash:restore'));

    expect(toast).toHaveBeenCalledExactlyOnceWith({ title: 'trash.restoreFailed', variant: 'destructive' });
  });

  it('purges a memory for good and confirms it', async () => {
    await openTrashTab();

    await click(button('trash:purge'));

    expect(storeActions.purgeMemory).toHaveBeenCalledExactlyOnceWith('trashed-1');
    expect(toast).toHaveBeenCalledExactlyOnceWith({ title: 'trash.purgeSuccess' });
  });

  it('reports a purge that failed', async () => {
    storeActions.purgeMemory.mockRejectedValue(new Error('locked'));
    await openTrashTab();

    await click(button('trash:purge'));

    expect(toast).toHaveBeenCalledExactlyOnceWith({ title: 'trash.purgeFailed', variant: 'destructive' });
  });

  it('requests the next archive page only while one exists', async () => {
    await patchStore({ archivedPagination: pageOf(2, true, 60) });
    await openTrashTab();

    await click(button('trash:more'));
    expect(storeActions.fetchArchivedMemories).toHaveBeenCalledExactlyOnceWith(3);

    storeActions.fetchArchivedMemories.mockClear();
    await patchStore({ archivedPagination: pageOf(3, false, 60) });
    await click(button('trash:more'));
    expect(storeActions.fetchArchivedMemories).not.toHaveBeenCalled();
  });
});

describe('MemorySection clear all', () => {
  const openClearDialog = async () => {
    renderSection();
    await click(byTitle('clearAll'));
  };

  it('asks for confirmation before anything is deleted', async () => {
    renderSection();
    expect(attr('clear-dialog', 'data-open')).toBe('false');

    await click(byTitle('clearAll'));
    expect(attr('clear-dialog', 'data-open')).toBe('true');
    expect(storeActions.deleteAllMemories).not.toHaveBeenCalled();

    await click(button('clear:close'));
    expect(attr('clear-dialog', 'data-open')).toBe('false');
  });

  it('deletes everything, refreshes the orphan check, confirms and closes the dialog', async () => {
    await openClearDialog();

    await click(button('clear:confirm'));

    expect(storeActions.deleteAllMemories).toHaveBeenCalledOnce();
    expect(world.retrieval.checkOrphanCollections).toHaveBeenCalledOnce();
    expect(toast).toHaveBeenCalledExactlyOnceWith({ title: 'clearAllSuccess', description: 'clearAllSuccessDesc' });
    expect(attr('clear-dialog', 'data-open')).toBe('false');
    expect(attr('clear-dialog', 'data-clearing')).toBe('false');
  });

  it('shows the dialog as busy while the deletion runs', async () => {
    const deletion = deferred<void>();
    storeActions.deleteAllMemories.mockReturnValue(deletion.promise);
    await openClearDialog();

    await click(button('clear:confirm'));
    expect(attr('clear-dialog', 'data-clearing')).toBe('true');

    deletion.resolve();
    await settle();
    expect(attr('clear-dialog', 'data-clearing')).toBe('false');
  });

  it('keeps the dialog open and skips the orphan check when the deletion fails', async () => {
    storeActions.deleteAllMemories.mockRejectedValue(new Error('denied'));
    await openClearDialog();

    await click(button('clear:confirm'));

    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'clearAllFailed',
      description: 'denied',
      variant: 'destructive',
    });
    expect(attr('clear-dialog', 'data-open')).toBe('true');
    expect(attr('clear-dialog', 'data-clearing')).toBe('false');
    expect(world.retrieval.checkOrphanCollections).not.toHaveBeenCalled();
  });

  it('styles the clear button as destructive with the readable text token', () => {
    renderSection();

    const clear = byTitle('clearAll');
    expect(clear).toHaveClass('hover:bg-destructive/10');
    expect(clear).not.toHaveClass('hover:bg-accent');
    const icon = screen.getByTitle('clearAll').querySelector('svg');
    expect(icon).toHaveClass('hover:text-destructive-text');
    expect(icon).not.toHaveClass('hover:text-destructive');
  });
});
