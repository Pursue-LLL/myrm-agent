/** @vitest-environment jsdom */
import { cleanup, screen, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { click, currentQuery, emitIngest, listAgents, resetKit, router, service } from './wikiSectionTestKit';
import { stubMounts } from './wikiSectionStubs';
import { agentOf, compileRunOf, richStats, snapshotOf, statsOf } from './wikiSectionFixtures';
import { call, props, renderShell, selectedTab, serveStats, statsReads } from './wikiShellBench';

vi.mock('../../WikiAgentScopeContext', async () => (await import('./wikiSectionStubs')).scopeProviderModule);

beforeEach(() => {
  resetKit();
  listAgents.mockResolvedValue({ items: [agentOf('a1', 'Alpha'), agentOf('a2', 'Beta')] });
});

afterEach(cleanup);

describe('WikiSection: frame', () => {
  it('provides the scope to the panels and follows scope changes made in the header', async () => {
    await renderShell();
    expect(props('WikiAgentScopeProvider')).toEqual({
      agentScopeId: null,
      scopeLabel: 'agentScopeDefault',
      scopeRevision: 1,
    });
    await click(screen.getByRole('option', { name: 'a1:Alpha:en' }));
    expect(currentQuery()).toBe('agentId=a1');
    expect(props('WikiAgentScopeProvider')).toEqual({
      agentScopeId: 'a1',
      scopeLabel: 'a1:Alpha:en',
      scopeRevision: 2,
    });
  });

  it('shows the header with the agents of the scope picker', async () => {
    await renderShell();
    expect(screen.getByRole('heading', { level: 2 }).textContent).toBe('title');
    const picker = document.querySelector<HTMLElement>('[data-slot="select"]') as HTMLElement;
    expect(
      within(picker)
        .getAllByRole('option')
        .map((option) => option.textContent),
    ).toEqual(['agentScopeDefault', 'a1:Alpha:en', 'a2:Beta:en']);
  });

  it('offers the five tabs with the overview first and selected', async () => {
    await renderShell();
    expect(
      within(screen.getByTestId('wiki-settings-shell'))
        .getAllByRole('tab')
        .map((tab) => tab.textContent),
    ).toEqual(['tabs.overview', 'tabs.concepts', 'tabs.pendingEdits', 'tabs.duplicateReview', 'tabs.queue']);
    expect(selectedTab()).toBe('tabs.overview');
    expect(screen.getByTestId('wiki-dedup-tab').textContent).toBe('tabs.duplicateReview');
  });

  it.each([
    ['tabs.concepts', 'concepts', 'WikiConceptsList'],
    ['tabs.pendingEdits', 'pendingEdits', 'WikiPendingEdits'],
    ['tabs.duplicateReview', 'duplicateReview', 'WikiDuplicateReviewPanel'],
    ['tabs.queue', 'queue', 'WikiQueuePanel'],
  ])('opens the %s tab, writes it to the URL and shows only its panel', async (label, param, panel) => {
    await renderShell();
    await click(screen.getByRole('tab', { name: label }));
    expect(selectedTab()).toBe(label);
    expect(currentQuery()).toBe(`wikiTab=${param}`);
    expect(
      screen
        .getAllByTestId(/^Wiki(ConceptsList|PendingEdits|DuplicateReviewPanel|QueuePanel)$/)
        .map((node) => node.dataset.testid),
    ).toEqual([panel]);
    expect(screen.queryByTestId('WikiLayersLedgerPanel')).toBeNull();
    await click(screen.getByRole('tab', { name: 'tabs.overview' }));
    expect(screen.getByTestId('WikiLayersLedgerPanel')).toBeTruthy();
  });

  it('keeps the import dialogs mounted on every tab, for the scope of the page', async () => {
    await renderShell('agentId=a1&wikiTab=queue');
    expect(props('WikiUrlImportDialog')).toMatchObject({ open: false, agentScopeId: 'a1' });
    expect(props('WikiVideoImportDialog')).toMatchObject({ open: false, agentScopeId: 'a1' });
    expect(props('WikiImportConflictDialog')).toMatchObject({ open: false, conflictPaths: [] });
    expect(props('WikiImportSecurityDialog')).toMatchObject({ open: false, blockedPaths: [], redactedPaths: [] });
  });
});

describe('WikiSection: overview layout', () => {
  it('stacks the overview cards in a fixed order', async () => {
    await renderShell();
    const markers = [
      screen.getByTestId('WikiLayersLedgerPanel'),
      screen.getByTestId('SecondBrainSetupCard'),
      screen.getByTestId('WikiSourceSyncPanel'),
      screen.getByTestId('ImaSourceCard'),
      screen.getByText('purpose.title'),
      screen.getByText('stats.title'),
      screen.getByTestId('ObsidianVaultActions'),
      screen.getByTestId('MeetingNotesImportCard'),
      screen.getByTestId('DailyReviewCard'),
      screen.getByText('query.title'),
      screen.getByText('actions.title'),
      screen.getByText('import.title'),
      screen.getByTestId('WikiIgnorePanel'),
      screen.getByText('import.obsidianTitle'),
    ];
    markers.slice(1).forEach((marker, index) => {
      expect(markers[index].compareDocumentPosition(marker) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    });
  });

  it('loads the purpose and the statistics into their cards', async () => {
    await renderShell();
    expect(screen.getByPlaceholderText<HTMLTextAreaElement>('purpose.placeholder').value).toBe('saved purpose');
    expect(screen.getByTestId('wiki-stats-panel')).toBeTruthy();
  });
});

describe('WikiSection: overview navigation', () => {
  it('opens a concept from the layers ledger in the concepts tab', async () => {
    await renderShell();
    await call('WikiLayersLedgerPanel', 'onOpenConcept', 'concepts/a.md');
    expect(selectedTab()).toBe('tabs.concepts');
    expect(currentQuery()).toBe('wikiTab=concepts&conceptPath=concepts%2Fa.md');
    expect(props('WikiConceptsList').highlightConceptPath).toBe('concepts/a.md');
  });

  it('refreshes the statistics and switches to the agent whose vault was just set up', async () => {
    await renderShell();
    const start = statsReads();
    await click(screen.getByRole('option', { name: 'a1:Alpha:en' }));
    const readsForAScopeChange = statsReads() - start;
    const beforeApplied = statsReads();
    await call('SecondBrainSetupCard', 'onApplied', 'a2');
    expect(statsReads() - beforeApplied).toBe(readsForAScopeChange + 1);
    expect(currentQuery()).toBe('agentId=a2');
  });

  it('scrolls to the Obsidian import card when asked to go to the import', async () => {
    await renderShell();
    const scrollIntoView = vi.fn();
    Object.defineProperty(document.getElementById('wiki-obsidian-import'), 'scrollIntoView', { value: scrollIntoView });
    await call('SecondBrainSetupCard', 'onGoToImport');
    expect(scrollIntoView).toHaveBeenCalledExactlyOnceWith({ behavior: 'smooth', block: 'start' });
  });

  it.each([
    ['SecondBrainSetupCard', 'onGoToProviders', '/settings/models'],
    ['WikiSourceSyncPanel', 'onGoToIntegrations', '/settings/credentials'],
  ])('sends %s.%s to %s', async (name, prop, path) => {
    await renderShell();
    await call(name, prop);
    expect(router.push).toHaveBeenCalledExactlyOnceWith(path);
  });

  it.each([
    ['SecondBrainSetupCard', 'onGoToDuplicateReview'],
    ['ImaSourceCard', 'onGoToDuplicateReview'],
  ])('opens the duplicate review for %s.%s', async (name, prop) => {
    await renderShell();
    await call(name, prop);
    expect(selectedTab()).toBe('tabs.duplicateReview');
    expect(currentQuery()).toBe('wikiTab=duplicateReview');
  });

  it.each([
    ['', '/library?tab=graph'],
    ['agentId=a1', '/library?tab=graph&agentId=a1'],
  ])('opens the knowledge graph for the URL "%s"', async (query, target) => {
    await renderShell(query);
    await call('SecondBrainSetupCard', 'onGoToGraph');
    expect(router.push).toHaveBeenCalledExactlyOnceWith(target);
  });

  it('opens the queue from the paused-compile banner', async () => {
    service.getQueueStatus.mockResolvedValue({
      stats: {},
      pending_items: [],
      failed_items: [],
      compile_run: compileRunOf({ state: 'paused' }),
    });
    await renderShell();
    await click(screen.getByRole('button', { name: 'compileRun.viewQueue' }));
    expect(selectedTab()).toBe('tabs.queue');
  });

  it('opens the synthesis review, pre-filtered, from the statistics badge', async () => {
    serveStats(richStats());
    await renderShell();
    await click(screen.getByRole('button', { name: /^stats\.synthesisPending/ }));
    expect(selectedTab()).toBe('tabs.pendingEdits');
    expect(props('WikiPendingEdits').initialFilter).toBe('synthesis');
  });

  it('opens the link import dialog from the batch import card', async () => {
    await renderShell();
    await click(screen.getByRole('button', { name: 'import.urls' }));
    expect(props('WikiUrlImportDialog').open).toBe(true);
    expect(props('WikiVideoImportDialog').open).toBe(false);
  });
});

describe('WikiSection: vault actions', () => {
  it('hands the vault state from the statistics to the Obsidian actions', async () => {
    serveStats(richStats({ wiki_path: '/vault/wiki' }));
    await renderShell('agentId=a1');
    expect(props('ObsidianVaultActions')).toEqual({
      agentScopeId: 'a1',
      wikiPath: '/vault/wiki',
      vaultReady: true,
      obsidianLaunchAvailable: true,
      vaultGitEnabled: true,
      vaultGitInitialized: true,
      vaultGitLastCommit: 'abc123',
    });
  });

  it('assumes nothing about the vault before the statistics are known', async () => {
    serveStats(new Error('statistics unavailable'));
    await renderShell();
    expect(props('ObsidianVaultActions')).toEqual({
      agentScopeId: null,
      wikiPath: undefined,
      vaultReady: false,
      obsidianLaunchAvailable: false,
      vaultGitEnabled: false,
      vaultGitInitialized: false,
      vaultGitLastCommit: null,
    });
  });

  it('treats missing optional vault flags as off', async () => {
    serveStats(statsOf({ vault_ready: false }));
    await renderShell();
    expect(props('ObsidianVaultActions')).toMatchObject({
      vaultReady: false,
      obsidianLaunchAvailable: false,
      vaultGitEnabled: false,
      vaultGitInitialized: false,
      vaultGitLastCommit: null,
    });
  });
});

describe('WikiSection: the other tabs', () => {
  it('shows the concepts of the scope, highlighting the one in the URL, and rebuilds the list when the scope changes', async () => {
    await renderShell('wikiTab=concepts&conceptPath=concepts%2Fa.md');
    expect(props('WikiConceptsList')).toMatchObject({
      agentScopeId: null,
      highlightConceptPath: 'concepts/a.md',
      treeSyncNonce: 0,
    });
    const mounted = stubMounts('WikiConceptsList');
    await click(screen.getByRole('option', { name: 'a1:Alpha:en' }));
    expect(props('WikiConceptsList').agentScopeId).toBe('a1');
    // 新范围先以旧修订号重建一次，修订号追上后再重建一次。
    expect(stubMounts('WikiConceptsList')).toBe(mounted + 2);
  });

  it('tells the concepts list when the trees were refreshed', async () => {
    await renderShell('wikiTab=concepts');
    await emitIngest(snapshotOf({}, { tree_sync_required: true }));
    expect(props('WikiConceptsList').treeSyncNonce).toBe(1);
  });

  it.each([
    ['concepts', 'WikiConceptsList'],
    ['pendingEdits', 'WikiPendingEdits'],
    ['duplicateReview', 'WikiDuplicateReviewPanel'],
  ])('rereads the statistics when the %s panel changes the vault', async (tab, panel) => {
    await renderShell(`wikiTab=${tab}`);
    const before = statsReads();
    await call(panel, 'onVaultMutated');
    expect(statsReads()).toBe(before + 1);
  });

  it.each([
    ['pendingEdits', 'WikiPendingEdits'],
    ['duplicateReview', 'WikiDuplicateReviewPanel'],
  ])('tells the %s panel which scope it works on', async (tab, panel) => {
    await renderShell(`agentId=a1&wikiTab=${tab}`);
    expect(props(panel)).toMatchObject({ agentScopeId: 'a1', scopeLabel: 'a1:Alpha:en' });
  });

  it('starts the pending edits unfiltered', async () => {
    await renderShell('wikiTab=pendingEdits');
    expect(props('WikiPendingEdits').initialFilter).toBe('all');
  });

  it('gives the queue the live ingest connection and its latest snapshot', async () => {
    await renderShell('agentId=a1&wikiTab=queue');
    expect(props('WikiQueuePanel')).toMatchObject({
      agentScopeId: 'a1',
      scopeLabel: 'a1:Alpha:en',
      liveIngestConnected: false,
      liveIngestSnapshot: null,
    });
    const snapshot = snapshotOf({ pending: 2 });
    await emitIngest(snapshot);
    expect(props('WikiQueuePanel')).toMatchObject({ liveIngestConnected: true, liveIngestSnapshot: snapshot });
  });

  it('highlights the raw file the URL points at in the statistics card', async () => {
    await renderShell('rawPath=raw%2Fa.md');
    expect(props('WikiRawSourceTree').highlightPath).toBe('raw/a.md');
  });
});
