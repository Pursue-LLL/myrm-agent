import { screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { deferred } from '@/test-utils/deferred';
import { elapse, settle, startFakeClock, stopFakeClock } from '@/test-utils/fakeClock';
import {
  attr,
  button,
  byTestId,
  click,
  openTab,
  patchStore,
  queryTestId,
  renderSection,
  resetKit,
  service,
  storeActions,
  typeInto,
  world,
} from './memorySectionTestKit';
import { memoryOf, pageOf } from './memorySectionFixtures';

const TOOLBAR_TITLES = [
  'import',
  'export',
  'exportMarkdown',
  'shareRulesTitle',
  'retry',
  'createDialog.title',
  'clearAll',
];

const openAllTab = async () => {
  const view = renderSection();
  await openTab('all');
  return view;
};

beforeEach(resetKit);

describe('MemorySection gating', () => {
  it('shows only the header and the toggles while memory is turned off', async () => {
    world.config.enableMemory = false;
    world.retrieval.embeddingApplied = false;
    renderSection();

    expect(attr('settings-toggles', 'data-enabled')).toBe('false');
    expect(queryTestId('tab-switcher')).toBeNull();
    expect(queryTestId('login-prompt')).toBeNull();
    expect(screen.queryByTitle('import')).toBeNull();
    expect(screen.queryByText('keywordModeHint')).toBeNull();
  });

  it('asks a signed-out user to log in and offers no toolbar', () => {
    world.auth.user = null;
    renderSection();

    expect(byTestId('login-prompt')).toHaveTextContent('loginRequired|loginRequiredDesc');
    expect(queryTestId('tab-switcher')).toBeNull();
    expect(screen.queryByTitle('import')).toBeNull();
    expect(storeActions.fetchPendingMemories).not.toHaveBeenCalled();
  });

  it('loads nothing for a signed-out visitor even with a ?tab= deep link', () => {
    world.auth.user = null;
    world.search = new URLSearchParams({ tab: 'all' });
    renderSection();

    expect(storeActions.fetchMemories).not.toHaveBeenCalled();
    expect(storeActions.fetchArchivedMemories).not.toHaveBeenCalled();
    expect(service.getMemoryTags).not.toHaveBeenCalled();
  });

  it('loads nothing before the auth state is initialised', () => {
    world.auth.isInitialized = false;
    renderSection();

    expect(storeActions.fetchPendingMemories).not.toHaveBeenCalled();
  });

  it('renders every memory card and the full toolbar for a signed-in user', () => {
    renderSection();

    for (const testId of [
      'working-state',
      'scope-hierarchy',
      'domain-mesh',
      'memory-stats',
      'taste-summary',
      'preference-stability',
      'tab-switcher',
    ]) {
      expect(byTestId(testId)).toBeInTheDocument();
    }
    for (const title of TOOLBAR_TITLES) {
      expect(screen.getByTitle(title)).toBeInTheDocument();
    }
    expect(queryTestId('command-center')).toBeNull();
  });

  it('keeps every toolbar button from submitting a surrounding form', () => {
    renderSection();

    for (const title of TOOLBAR_TITLES) {
      expect(screen.getByTitle(title)).toHaveAttribute('type', 'button');
    }
  });

  it('shows the command center only when the memory labs flag is on', () => {
    world.labsEnabled = true;
    renderSection();

    expect(byTestId('command-center')).toBeInTheDocument();
  });

  it('hints at keyword retrieval only while no embedding model is applied', () => {
    world.retrieval.embeddingApplied = false;
    const { unmount } = renderSection();
    expect(screen.getByText('keywordModeHint')).toBeInTheDocument();
    unmount();

    world.retrieval.embeddingApplied = true;
    renderSection();
    expect(screen.queryByText('keywordModeHint')).toBeNull();
  });

  it('feeds the tab switcher the pending, total and archived counts', async () => {
    renderSection();
    expect(attr('tab-switcher', 'data-total')).toBe('');

    await patchStore({
      pendingCount: 4,
      memoryPagination: pageOf(1, false, 12),
      archivedPagination: pageOf(1, false, 3),
    });

    expect(attr('tab-switcher', 'data-pending')).toBe('4');
    expect(attr('tab-switcher', 'data-total')).toBe('12');
    expect(attr('tab-switcher', 'data-archived')).toBe('3');
  });
});

describe('MemorySection tabs and data loading', () => {
  it('starts on the pending tab and loads only the pending memories', () => {
    renderSection();

    expect(attr('tab-switcher', 'data-active')).toBe('pending');
    expect(attr('pending-list', 'data-batch')).toBe('true');
    expect(storeActions.fetchPendingMemories).toHaveBeenCalledOnce();
    expect(storeActions.fetchMemories).not.toHaveBeenCalled();
    expect(storeActions.fetchArchivedMemories).not.toHaveBeenCalled();
  });

  it('shows the panel that belongs to each tab', async () => {
    renderSection();

    await openTab('context');
    expect(byTestId('context-panel')).toBeInTheDocument();
    expect(queryTestId('pending-list')).toBeNull();

    await openTab('shared');
    expect(byTestId('shared-context')).toBeInTheDocument();
    expect(queryTestId('context-panel')).toBeNull();

    await openTab('recall');
    expect(byTestId('recall-panel')).toBeInTheDocument();

    await openTab('trash');
    expect(byTestId('trash-panel')).toBeInTheDocument();

    await openTab('all');
    expect(screen.getByPlaceholderText('searchPlaceholder')).toBeInTheDocument();
    expect(queryTestId('trash-panel')).toBeNull();
  });

  it('loads memories and the popular tags when the all tab opens', async () => {
    await openAllTab();

    expect(storeActions.fetchMemories).toHaveBeenCalledOnce();
    expect(service.getMemoryTags).toHaveBeenCalledExactlyOnceWith(20);
  });

  it('loads the archived memories when the trash tab opens', async () => {
    renderSection();
    await openTab('trash');

    expect(storeActions.fetchArchivedMemories).toHaveBeenCalledOnce();
    expect(storeActions.fetchMemories).not.toHaveBeenCalled();
  });

  it('keeps the list usable when the tag statistics fail to load', async () => {
    service.getMemoryTags.mockRejectedValue(new Error('tags down'));
    await openAllTab();

    expect(screen.queryByText('tags:')).toBeNull();
    expect(screen.getByText('noMemories')).toBeInTheDocument();
  });

  it.each([
    ['trash', 'fetchArchivedMemories'],
    ['all', 'fetchMemories'],
  ] as const)('honours the ?tab=%s deep link on mount', (tab, expectedFetch) => {
    world.search = new URLSearchParams({ tab });
    renderSection();

    expect(attr('tab-switcher', 'data-active')).toBe(tab);
    expect(storeActions[expectedFetch]).toHaveBeenCalled();
  });

  it('ignores a ?tab= value that is not a tab', () => {
    world.search = new URLSearchParams({ tab: 'bogus' });
    renderSection();

    expect(attr('tab-switcher', 'data-active')).toBe('pending');
  });

  it.each([
    ['pending', 'fetchPendingMemories'],
    ['trash', 'fetchArchivedMemories'],
    ['all', 'fetchMemories'],
    ['context', 'fetchMemories'],
    ['shared', 'fetchMemories'],
    ['recall', 'fetchMemories'],
  ] as const)('refreshes the %s tab through %s', async (tab, expectedFetch) => {
    renderSection();
    await openTab(tab);
    for (const action of Object.values(storeActions)) {
      action.mockClear();
    }

    await click(screen.getByTitle('retry'));

    expect(storeActions[expectedFetch]).toHaveBeenCalledOnce();
  });
});

describe('MemorySection refresh feedback', () => {
  it('spins the refresh icon and disables the button until the reload finishes', async () => {
    renderSection();
    const reload = deferred<void>();
    storeActions.fetchPendingMemories.mockReturnValueOnce(reload.promise);

    await click(screen.getByTitle('retry'));
    expect(screen.getByTitle('retry')).toBeDisabled();
    expect(screen.getByTitle('retry').querySelector('svg')).toHaveClass('animate-spin');

    reload.resolve();
    await settle();
    expect(screen.getByTitle('retry')).toBeEnabled();
    expect(screen.getByTitle('retry').querySelector('svg')).not.toHaveClass('animate-spin');
  });
});

describe('MemorySection search debounce', () => {
  beforeEach(startFakeClock);
  afterEach(stopFakeClock);

  it('writes the search text to the store only after it has settled', async () => {
    await openAllTab();

    await typeInto(screen.getByPlaceholderText('searchPlaceholder'), 'sushi');
    await elapse(299);
    expect(storeActions.setMemorySearchQuery).not.toHaveBeenCalled();

    await elapse(1);
    expect(storeActions.setMemorySearchQuery).toHaveBeenCalledExactlyOnceWith('sushi');
  });

  it('drops a pending search when the user leaves the all tab before it settled', async () => {
    await openAllTab();

    await typeInto(screen.getByPlaceholderText('searchPlaceholder'), 'sushi');
    await elapse(100);
    await openTab('recall');
    await elapse(1000);

    expect(storeActions.setMemorySearchQuery).not.toHaveBeenCalled();
  });

  it('keeps the typed text when the user leaves and returns to the all tab', async () => {
    await openAllTab();
    await typeInto(screen.getByPlaceholderText('searchPlaceholder'), 'sushi');
    await elapse(300);
    storeActions.setMemorySearchQuery.mockClear();

    await openTab('recall');
    await elapse(300);
    await openTab('all');
    await elapse(300);

    expect(screen.getByPlaceholderText('searchPlaceholder')).toHaveValue('sushi');
    expect(storeActions.setMemorySearchQuery).not.toHaveBeenCalled();
  });
});

describe('MemorySection dialogs', () => {
  it.each([
    ['guide', () => button('guide.openGuideHint'), 'guide'],
    ['share rules', () => screen.getByTitle('shareRulesTitle'), 'share-rules'],
    ['create memory', () => screen.getByTitle('createDialog.title'), 'create-dialog'],
  ])('opens and closes the %s dialog', async (_label, opener, testId) => {
    renderSection();
    expect(attr(testId, 'data-open')).toBe('false');

    await click(opener());
    expect(attr(testId, 'data-open')).toBe('true');

    await click(button(`${testId}:close`));
    expect(attr(testId, 'data-open')).toBe('false');
  });

  it('opens the detail sheet and the edit dialog for the clicked memory and closes them again', async () => {
    renderSection();
    await patchStore({ memories: [memoryOf('m1'), memoryOf('m2')] });
    await openTab('all');

    await click(button('open m2'));
    expect(attr('detail-sheet', 'data-memory')).toBe('m2');
    expect(attr('detail-sheet', 'data-open')).toBe('true');
    await click(button('detail-sheet:close'));
    expect(attr('detail-sheet', 'data-open')).toBe('false');

    await click(button('edit m1'));
    expect(attr('edit-dialog', 'data-memory')).toBe('m1');
    expect(attr('edit-dialog', 'data-open')).toBe('true');
    await click(button('edit-dialog:close'));
    expect(attr('edit-dialog', 'data-open')).toBe('false');
  });
});
