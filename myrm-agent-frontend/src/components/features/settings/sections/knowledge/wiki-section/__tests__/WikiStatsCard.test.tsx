/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { click, resetKit, world } from './wikiSectionTestKit';
import { stubProps } from './wikiSectionStubs';
import { healthOf, richStats, statsOf } from './wikiSectionFixtures';
import { WikiStatsCard } from '../WikiStatsCard';
import { formatCognitiveUpdatedAt } from '../wikiStatsFormat';
import type { TreeNode, WikiHealthReport } from '@/services/wikiService';
import type { WikiStats } from '../types';

type CardProps = Parameters<typeof WikiStatsCard>[0];
type OverviewOver = Partial<CardProps['overview']>;
type MaintenanceOver = Partial<CardProps['maintenance']>;
type TabsOver = Partial<CardProps['tabs']>;

interface HealthSectionProps {
  report: WikiHealthReport | null;
  isLoading: boolean;
  loadError: boolean;
  expanded: boolean;
  isRecompiling: boolean;
  isRepairing: boolean;
  onToggleExpanded: () => void;
  onRecompile: () => void;
  onRepair: () => void;
  onNavigateIssue: unknown;
  onOpenDuplicateReview: unknown;
  onOpenPendingEdits: () => void;
  onRefresh: () => void;
}

interface RawTreeProps {
  treeData: unknown;
  isLoading: boolean;
  agentScopeId: string | null;
  highlightPath: string | null;
  onRawDeleted: () => void;
}

function renderCard(
  over: { overview?: OverviewOver; maintenance?: MaintenanceOver; tabs?: TabsOver; scope?: string | null } = {},
) {
  const overview: CardProps['overview'] = {
    stats: statsOf(),
    isLoadingStats: false,
    loadStats: vi.fn(),
    healthReport: healthOf(),
    isLoadingHealthReport: false,
    healthReportLoadError: false,
    healthReportExpanded: false,
    setHealthReportExpanded: vi.fn(),
    loadHealthReport: vi.fn(),
    rawTreeData: [],
    isLoadingRawTree: false,
    refreshIngestTreesSilently: vi.fn(),
    synthesisPendingCount: 0,
    duplicateGroupsPending: 0,
    dedupBlocksCompile: false,
    ...over.overview,
  };
  const maintenance: CardProps['maintenance'] = {
    isCompiling: false,
    handleCompile: vi.fn(),
    isRepairingTypes: false,
    handleRepairPageTypes: vi.fn(),
    ...over.maintenance,
  };
  const tabs: CardProps['tabs'] = {
    rawPathFromUrl: null,
    navigateToHealthIssue: vi.fn(),
    handleOpenSynthesisPending: vi.fn(),
    handleOpenDuplicateReview: vi.fn(),
    handleWikiTabChange: vi.fn(),
    ...over.tabs,
  };
  render(
    <WikiStatsCard
      agentScopeId={over.scope === undefined ? 'a1' : over.scope}
      overview={overview}
      maintenance={maintenance}
      tabs={tabs}
    />,
  );
  return { overview, maintenance, tabs };
}

const healthSection = () => stubProps<HealthSectionProps & Record<string, unknown>>('WikiHealthIssuesSection');
const rawTree = () => stubProps<RawTreeProps & Record<string, unknown>>('WikiRawSourceTree');

beforeEach(resetKit);
afterEach(cleanup);

describe('WikiStatsCard: loading the statistics', () => {
  it('offers to load the statistics before they are known', async () => {
    const { overview } = renderCard({ overview: { stats: null } });
    expect(screen.queryByTestId('wiki-stats-panel')).toBeNull();
    expect(screen.queryByTestId('wiki-stats-loading')).toBeNull();
    await click(screen.getByTestId('wiki-load-stats-btn'));
    expect(overview.loadStats).toHaveBeenCalledOnce();
    expect(screen.getByText('actions.loadStats')).toBeTruthy();
  });

  it('shows a placeholder instead of the load button while loading', () => {
    renderCard({ overview: { stats: null, isLoadingStats: true } });
    expect(screen.getByTestId('wiki-stats-loading').textContent).toBe('loading');
    expect(screen.queryByTestId('wiki-load-stats-btn')).toBeNull();
    expect(screen.queryByTestId('wiki-stats-panel')).toBeNull();
  });

  it('keeps the known statistics on screen while they reload', () => {
    renderCard({ overview: { isLoadingStats: true } });
    expect(screen.getByTestId('wiki-stats-loading')).toBeTruthy();
    expect(screen.getByTestId('wiki-stats-panel')).toBeTruthy();
    expect(screen.queryByTestId('wiki-load-stats-btn')).toBeNull();
  });

  it('shows the panel, not the load button, once the statistics are known', () => {
    renderCard();
    expect(screen.getByTestId('wiki-stats-panel')).toBeTruthy();
    expect(screen.queryByTestId('wiki-load-stats-btn')).toBeNull();
    expect(screen.queryByTestId('wiki-stats-loading')).toBeNull();
    expect(screen.getByText('stats.title')).toBeTruthy();
    expect(screen.getByText('stats.description')).toBeTruthy();
  });

  it('reloads from the refresh button', async () => {
    const { overview } = renderCard();
    await click(screen.getByRole('button', { name: 'actions.refresh' }));
    expect(overview.loadStats).toHaveBeenCalledOnce();
  });
});

describe('WikiStatsCard: the numbers', () => {
  it('shows the concept, article and raw file counts with their labels', () => {
    renderCard({ overview: { stats: statsOf({ total_concepts: 11, total_articles: 22, total_raw_files: 33 }) } });
    for (const [count, label] of [
      ['11', 'stats.concepts'],
      ['22', 'stats.articles'],
      ['33', 'stats.rawFiles'],
    ]) {
      expect(screen.getByText(count).nextElementSibling?.textContent).toBe(label);
    }
  });

  it.each([
    [true, 'stats.cognitiveReady', 'text-emerald-600'],
    [false, 'stats.cognitivePending', 'text-amber-700'],
  ])('shows the cognitive index as %s with the matching colour', (ready, label, tone) => {
    renderCard({ overview: { stats: statsOf({ cognitive_index_ready: ready }) } });
    expect(screen.getByText(label).className).toContain(tone);
  });

  it.each([
    [7, 'stats.cognitiveLogEntries|{"count":7}'],
    [undefined, 'stats.cognitiveLogEntries|{"count":0}'],
  ])('shows %s cognitive log entries', (entries, label) => {
    renderCard({ overview: { stats: statsOf({ cognitive_log_entries: entries }) } });
    expect(screen.getByText(label)).toBeTruthy();
  });

  it.each(['en', 'ja'])('says when the hot index was updated, in the %s locale', (locale) => {
    world.locale = locale;
    const updatedAt = '2026-05-06T07:08:09Z';
    renderCard({ overview: { stats: statsOf({ cognitive_hot_updated_at: updatedAt }) } });
    const time = formatCognitiveUpdatedAt(updatedAt, locale);
    expect(screen.getByText(`stats.cognitiveHotUpdated|${JSON.stringify({ time })}`)).toBeTruthy();
    expect(screen.queryByText('stats.cognitiveHotEmpty')).toBeNull();
  });

  it.each([[null], [undefined]])('says the hot index is empty without an update time (%s)', (updatedAt) => {
    renderCard({ overview: { stats: statsOf({ cognitive_hot_updated_at: updatedAt }) } });
    expect(screen.getByText('stats.cognitiveHotEmpty')).toBeTruthy();
    expect(screen.queryByText(/^stats\.cognitiveHotUpdated/)).toBeNull();
  });

  it('explains the raw source colours', () => {
    renderCard();
    for (const key of [
      'concepts.rawSourcesTitle',
      'concepts.rawIngestNotCompiled',
      'concepts.rawIngestClean',
      'concepts.rawIngestModified',
    ]) {
      expect(screen.getByText(key)).toBeTruthy();
    }
  });
});

describe('WikiStatsCard: badges', () => {
  it('passes the review counts to the badges and opens the matching review', async () => {
    const stats: Partial<WikiStats> = richStats();
    const { tabs } = renderCard({
      overview: {
        stats: statsOf(stats),
        synthesisPendingCount: 3,
        duplicateGroupsPending: 2,
        dedupBlocksCompile: true,
      },
    });
    await click(screen.getByRole('button', { name: 'stats.synthesisPending|{"count":3}' }));
    expect(tabs.handleOpenSynthesisPending).toHaveBeenCalledOnce();
    const duplicates = screen.getByRole('button', { name: 'stats.duplicateGroupsPending|{"count":2}' });
    expect(duplicates.className).toContain('bg-rose-500/10');
    await click(duplicates);
    expect(tabs.handleOpenDuplicateReview).toHaveBeenCalledOnce();
  });

  it.each([
    ['a health report is loaded', { healthReport: healthOf() }],
    ['a health report is on its way', { healthReport: null, isLoadingHealthReport: true }],
    ['loading the health report failed', { healthReport: null, healthReportLoadError: true }],
  ])('does not hint at running a health report when %s', (_label, over) => {
    renderCard({ overview: { stats: richStats(), ...over } });
    expect(screen.queryByText('stats.structuralHint')).toBeNull();
  });

  it('hints at the health report when issues exist and none has been loaded or is on its way', () => {
    renderCard({ overview: { stats: richStats(), healthReport: null, isLoadingHealthReport: false } });
    expect(screen.getByText('stats.structuralHint')).toBeTruthy();
  });
});

describe('WikiStatsCard: health issues', () => {
  it.each([
    ['a report exists', { healthReport: healthOf() }, false],
    ['no report yet and no failure', { healthReport: null }, true],
    ['no report because loading failed', { healthReport: null, healthReportLoadError: true }, false],
    ['a report is being refreshed', { healthReport: healthOf(), isLoadingHealthReport: true }, true],
  ])('with %s the section is loading = %s', (_label, over, loading) => {
    renderCard({ overview: over });
    expect(healthSection().isLoading).toBe(loading);
  });

  it('hands the report, its load error and its expansion to the section', () => {
    const report = healthOf({ issues_found: 4 });
    renderCard({ overview: { healthReport: report, healthReportLoadError: true, healthReportExpanded: true } });
    expect(healthSection().report).toBe(report);
    expect(healthSection().loadError).toBe(true);
    expect(healthSection().expanded).toBe(true);
  });

  it('flips the expansion with an updater so rapid clicks cannot lose a toggle', () => {
    const { overview } = renderCard();
    healthSection().onToggleExpanded();
    const update = vi.mocked(overview.setHealthReportExpanded).mock.calls[0][0] as (open: boolean) => boolean;
    expect([update(false), update(true)]).toEqual([true, false]);
  });

  it('runs the recompile and the page type repair without passing anything along', () => {
    const { maintenance } = renderCard({ maintenance: { isCompiling: true, isRepairingTypes: true } });
    expect(healthSection().isRecompiling).toBe(true);
    expect(healthSection().isRepairing).toBe(true);
    healthSection().onRecompile();
    healthSection().onRepair();
    expect(maintenance.handleCompile).toHaveBeenCalledExactlyOnceWith();
    expect(maintenance.handleRepairPageTypes).toHaveBeenCalledExactlyOnceWith();
  });

  it('shows the section as idle when nothing is running', () => {
    renderCard();
    expect(healthSection().isRecompiling).toBe(false);
    expect(healthSection().isRepairing).toBe(false);
  });

  it('routes issue navigation, the duplicate review, pending edits and refresh to the right places', () => {
    const { overview, tabs } = renderCard();
    expect(healthSection().onNavigateIssue).toBe(tabs.navigateToHealthIssue);
    expect(healthSection().onOpenDuplicateReview).toBe(tabs.handleOpenDuplicateReview);
    healthSection().onOpenPendingEdits();
    expect(tabs.handleWikiTabChange).toHaveBeenCalledExactlyOnceWith('pendingEdits');
    healthSection().onRefresh();
    expect(overview.loadHealthReport).toHaveBeenCalledExactlyOnceWith();
  });
});

describe('WikiStatsCard: raw source tree', () => {
  it('shows the tree of the scope, highlighting the file the URL points at', () => {
    const tree: TreeNode[] = [{ id: 'raw', name: 'raw', is_dir: true, children: [] }];
    renderCard({
      scope: 'a1',
      overview: { rawTreeData: tree, isLoadingRawTree: true },
      tabs: { rawPathFromUrl: 'raw/a.md' },
    });
    expect(rawTree().treeData).toBe(tree);
    expect(rawTree().isLoading).toBe(true);
    expect(rawTree().agentScopeId).toBe('a1');
    expect(rawTree().highlightPath).toBe('raw/a.md');
  });

  it('passes the default scope on as null', () => {
    renderCard({ scope: null });
    expect(rawTree().agentScopeId).toBeNull();
    expect(rawTree().highlightPath).toBeNull();
  });

  it('refreshes the trees silently after a raw file is deleted', () => {
    const { overview } = renderCard();
    rawTree().onRawDeleted();
    expect(overview.refreshIngestTreesSilently).toHaveBeenCalledExactlyOnceWith();
  });
});
