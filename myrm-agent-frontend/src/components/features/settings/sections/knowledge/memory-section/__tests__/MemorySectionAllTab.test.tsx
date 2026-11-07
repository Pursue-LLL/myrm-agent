import { fireEvent, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import {
  button,
  click,
  openTab,
  patchStore,
  renderSection,
  resetKit,
  routerPush,
  service,
  setInputMessage,
  storeActions,
  toast,
  toastArgs,
  typeInto,
} from './memorySectionTestKit';
import { memoryOf, pageOf } from './memorySectionFixtures';

const openAllTab = async () => {
  renderSection();
  await openTab('all');
};

beforeEach(resetKit);

describe('MemorySection all tab list', () => {
  it('shows a loading state while the first page loads', async () => {
    await patchStore({ memoriesLoading: true });
    await openAllTab();

    expect(screen.getByText('loading')).toBeInTheDocument();
    expect(screen.queryByText('noMemories')).toBeNull();
  });

  it('explains an empty list once loading has finished', async () => {
    await openAllTab();

    expect(screen.getByText('noMemories')).toBeInTheDocument();
    expect(screen.getByText('noMemoriesDesc')).toBeInTheDocument();
    expect(screen.queryByText('loading')).toBeNull();
  });

  it('renders one confirmed card per memory', async () => {
    await patchStore({ memories: [memoryOf('m1'), memoryOf('m2')] });
    await openAllTab();

    for (const id of ['m1', 'm2']) {
      expect(screen.getByTestId(`card-${id}`)).toHaveAttribute('data-variant', 'confirmed');
    }
  });

  it('offers to load more only while another page exists', async () => {
    await patchStore({ memories: [memoryOf('m1')], memoryPagination: pageOf(1, false) });
    await openAllTab();
    expect(screen.queryByRole('button', { name: 'loadMore' })).toBeNull();

    await patchStore({ memoryPagination: pageOf(1, true, 40) });
    await click(button('loadMore'));
    expect(storeActions.loadMoreMemories).toHaveBeenCalledOnce();
  });

  it('disables the load-more button and shows progress while the next page loads', async () => {
    await patchStore({ memories: [memoryOf('m1')], memoryPagination: pageOf(1, true, 40), memoriesLoading: true });
    await openAllTab();

    const loadMore = screen.getByRole('button', { name: 'loading' });
    expect(loadMore).toBeDisabled();
    expect(loadMore.querySelector('svg')).toHaveClass('animate-spin');
  });
});

describe('MemorySection all tab filters', () => {
  it('filters by memory type and marks the active type', async () => {
    await openAllTab();
    expect(button('filterAll')).toHaveClass('bg-background');

    await click(button('types.semantic'));
    expect(storeActions.setMemoryTypeFilter).toHaveBeenLastCalledWith('semantic');
    expect(button('types.semantic')).toHaveClass('bg-background');
    expect(button('filterAll')).not.toHaveClass('bg-background');

    await click(button('filterAll'));
    expect(storeActions.setMemoryTypeFilter).toHaveBeenLastCalledWith(null);
  });

  it('offers every memory type as a filter', async () => {
    await openAllTab();

    for (const type of ['profile', 'semantic', 'episodic', 'procedural', 'conversation', 'claim', 'task_digest']) {
      expect(button(`types.${type}`)).toBeInTheDocument();
    }
  });

  it('changes the sort field and toggles the sort direction', async () => {
    await openAllTab();
    const select = screen.getByRole('combobox');
    expect(select).toHaveValue('created_at');

    fireEvent.change(select, { target: { value: 'importance' } });
    expect(storeActions.setMemorySortBy).toHaveBeenCalledExactlyOnceWith('importance');

    await click(screen.getByTitle('sortDescending'));
    expect(storeActions.setMemorySortOrder).toHaveBeenLastCalledWith('asc');

    await click(screen.getByTitle('sortAscending'));
    expect(storeActions.setMemorySortOrder).toHaveBeenLastCalledWith('desc');
  });

  it('hides the tag filter until the server reports tags', async () => {
    await openAllTab();

    expect(screen.queryByText('tags:')).toBeNull();
  });

  it('lists the ten most used tags with their counts and filters by the clicked one', async () => {
    service.getMemoryTags.mockResolvedValue({
      tags: Array.from({ length: 12 }, (_, index) => ({ tag: `tag-${index}`, count: 12 - index })),
    });
    await openAllTab();
    const chip = (tag: string) => screen.getByText(tag, { selector: 'button' });

    expect(screen.getByText('tags:')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'filterAll' })[1]).toHaveClass('bg-primary/10');
    expect(chip('tag-0').querySelector('span')).toHaveTextContent('12');
    expect(chip('tag-9').querySelector('span')).toHaveTextContent('3');
    expect(screen.queryByText('tag-10')).toBeNull();

    await click(chip('tag-3'));
    expect(storeActions.setMemoryTagFilter).toHaveBeenLastCalledWith('tag-3');
    expect(chip('tag-3')).toHaveClass('bg-primary/10');
    expect(screen.getAllByRole('button', { name: 'filterAll' })[1]).not.toHaveClass('bg-primary/10');

    await click(chip('tag-3'));
    expect(storeActions.setMemoryTagFilter).toHaveBeenLastCalledWith(null);
  });

  it('clears the tag filter through the all chip', async () => {
    service.getMemoryTags.mockResolvedValue({ tags: [{ tag: 'travel', count: 2 }] });
    await patchStore({ memoryTagFilter: 'travel' });
    await openAllTab();
    const [, allTagsChip] = screen.getAllByRole('button', { name: 'filterAll' });

    await click(allTagsChip);

    expect(storeActions.setMemoryTagFilter).toHaveBeenCalledExactlyOnceWith(null);
  });

  it('shows what the user types in the search box', async () => {
    await openAllTab();
    const input = screen.getByPlaceholderText('searchPlaceholder');

    await typeInto(input, 'visa');

    expect(input).toHaveValue('visa');
  });
});

describe('MemorySection memory actions', () => {
  beforeEach(async () => {
    await patchStore({
      memories: [
        memoryOf('m1'),
        memoryOf('e1', { memory_type: 'episodic' }),
        memoryOf('p1', { memory_type: 'procedural' }),
      ],
    });
    await openAllTab();
    storeActions.fetchMemories.mockClear();
  });

  it('deletes permanently with a purge confirmation', async () => {
    await click(button('purge m1'));

    expect(storeActions.deleteMemory).toHaveBeenCalledExactlyOnceWith('m1', 'semantic', true);
    expect(toast).toHaveBeenCalledExactlyOnceWith({ title: 'deleteSuccess', description: 'trash.purgeSuccess' });
  });

  it('soft-deletes semantic memories and lets the user undo from the toast', async () => {
    await click(button('delete m1'));

    expect(storeActions.deleteMemory).toHaveBeenCalledExactlyOnceWith('m1', 'semantic', false);
    const [shown] = toastArgs();
    expect(shown).toMatchObject({ title: 'deleteSuccess', description: 'trash.undoHint' });
    expect(shown.action?.label).toBe('trash.undo');

    await shown.action?.onClick();
    expect(service.restoreMemory).toHaveBeenCalledExactlyOnceWith('m1');
    expect(storeActions.fetchMemories).toHaveBeenCalledOnce();
    expect(toast).toHaveBeenLastCalledWith({ title: 'trash.restoreSuccess' });
  });

  it('reports a failed undo', async () => {
    service.restoreMemory.mockRejectedValue(new Error('gone'));
    await click(button('delete m1'));

    await toastArgs()[0].action?.onClick();

    expect(toast).toHaveBeenLastCalledWith({ title: 'trash.restoreFailed', variant: 'destructive' });
  });

  it('offers the undo for episodic memories as well', async () => {
    await click(button('delete e1'));

    expect(storeActions.deleteMemory).toHaveBeenCalledExactlyOnceWith('e1', 'episodic', false);
    expect(toastArgs()[0].action?.label).toBe('trash.undo');
  });

  it('deletes other memory types for good without an undo', async () => {
    await click(button('delete p1'));

    expect(storeActions.deleteMemory).toHaveBeenCalledExactlyOnceWith('p1', 'procedural', false);
    expect(toast).toHaveBeenCalledExactlyOnceWith({ title: 'deleteSuccess', description: 'deleteSuccessDesc' });
  });

  it.each([
    ['an Error', new Error('boom'), 'boom'],
    ['something else', 'nope', 'unknownError'],
  ])('reports a failed delete caused by %s', async (_label, failure, expectedText) => {
    storeActions.deleteMemory.mockRejectedValue(failure);

    await click(button('purge m1'));

    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'deleteFailed',
      description: expectedText,
      variant: 'destructive',
    });
  });

  it('disables an active memory and re-enables a disabled one', async () => {
    await click(button('toggle m1'));
    expect(service.updateMemoryStatus).toHaveBeenLastCalledWith('m1', 'disabled');
    expect(toast).toHaveBeenLastCalledWith({ title: 'disableSuccess', description: 'disableSuccessDesc' });

    await patchStore({ memories: [memoryOf('m1', { status: 'disabled' })] });
    await click(button('toggle m1'));
    expect(service.updateMemoryStatus).toHaveBeenLastCalledWith('m1', 'active');
    expect(toast).toHaveBeenLastCalledWith({ title: 'enableSuccess', description: 'enableSuccessDesc' });
    expect(storeActions.fetchMemories).toHaveBeenCalledTimes(2);
  });

  it('reports a failed status change and skips the reload', async () => {
    service.updateMemoryStatus.mockRejectedValue(new Error('locked'));

    await click(button('toggle m1'));

    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'statusUpdateFailed',
      description: 'locked',
      variant: 'destructive',
    });
    expect(storeActions.fetchMemories).not.toHaveBeenCalled();
  });

  it('protects and releases a rule', async () => {
    await click(button('protect m1'));
    expect(service.updateMemory).toHaveBeenLastCalledWith('semantic', 'm1', { is_user_locked: true });
    expect(toast).toHaveBeenLastCalledWith({ title: 'protectRuleSuccess', description: 'protectRuleSuccessDesc' });

    await click(button('unprotect m1'));
    expect(service.updateMemory).toHaveBeenLastCalledWith('semantic', 'm1', { is_user_locked: false });
    expect(toast).toHaveBeenLastCalledWith({
      title: 'releaseProtectionSuccess',
      description: 'releaseProtectionSuccessDesc',
    });
    expect(storeActions.fetchMemories).toHaveBeenCalledTimes(2);
  });

  it('protects a memory through the endpoint of its own type', async () => {
    await click(button('protect p1'));

    expect(service.updateMemory).toHaveBeenCalledExactlyOnceWith('procedural', 'p1', { is_user_locked: true });
  });

  it('reports a failed protection change', async () => {
    service.updateMemory.mockRejectedValue(new Error('read only'));

    await click(button('protect m1'));

    expect(toast).toHaveBeenCalledExactlyOnceWith({
      title: 'statusUpdateFailed',
      description: 'read only',
      variant: 'destructive',
    });
  });

  it('continues a memory in the chat composer', async () => {
    await click(button('chat m1'));

    expect(setInputMessage).toHaveBeenCalledExactlyOnceWith('content of m1');
    expect(routerPush).toHaveBeenCalledExactlyOnceWith('/');
  });
});
