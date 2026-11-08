/** @vitest-environment jsdom */
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { click, resetKit, world } from './wikiSectionTestKit';
import { healthOf, statsOf } from './wikiSectionFixtures';
import { WikiStatsBadges } from '../WikiStatsBadges';
import { formatCognitiveUpdatedAt } from '../wikiStatsFormat';
import type { WikiStats } from '../types';

type BadgesProps = Parameters<typeof WikiStatsBadges>[0];

function renderBadges(stats: Partial<WikiStats> = {}, over: Partial<BadgesProps> = {}) {
  const onOpenSynthesisPending = vi.fn();
  const onOpenDuplicateReview = vi.fn();
  render(
    <WikiStatsBadges
      stats={statsOf(stats)}
      healthReport={null}
      isLoadingHealthReport={false}
      healthReportLoadError={false}
      synthesisPendingCount={0}
      duplicateGroupsPending={0}
      dedupBlocksCompile={false}
      onOpenSynthesisPending={onOpenSynthesisPending}
      onOpenDuplicateReview={onOpenDuplicateReview}
      {...over}
    />,
  );
  return { onOpenSynthesisPending, onOpenDuplicateReview };
}

const text = (content: string) => screen.queryByText(content);

beforeEach(resetKit);
afterEach(cleanup);

describe('WikiStatsBadges: vault and migration', () => {
  it.each([
    [true, 'stats.vaultReady', 'stats.vaultNotReady', 'bg-emerald-500/10'],
    [false, 'stats.vaultNotReady', 'stats.vaultReady', 'bg-amber-500/10'],
  ])('with vault ready = %s it says %s in the matching colour', (ready, shown, hidden, tone) => {
    renderBadges({ vault_ready: ready });
    expect(text(shown)?.className).toContain(tone);
    expect(text(hidden)).toBeNull();
  });

  it.each([
    [true, 'stats.legacyMigrated', 'stats.legacyPending', 'bg-emerald-500/10'],
    [false, 'stats.legacyPending', 'stats.legacyMigrated', 'bg-amber-500/10'],
  ])('with legacy migrated = %s it says %s in the matching colour', (migrated, shown, hidden, tone) => {
    renderBadges({ legacy_migrated: migrated });
    expect(text(shown)?.className).toContain(tone);
    expect(text(hidden)).toBeNull();
  });
});

describe('WikiStatsBadges: structural issues and assets', () => {
  it('shows no issue badge for a clean vault', () => {
    renderBadges();
    for (const key of ['stats.brokenLinks', 'stats.invalidPageTypes', 'stats.provenanceGaps']) {
      expect(screen.queryByText(new RegExp(`^${key}`))).toBeNull();
    }
  });

  it('shows a badge with its count for each kind of structural issue', () => {
    renderBadges({
      structural_issues: { broken_links: 2, invalid_frontmatter_types: 3, provenance_gaps: 4, scanned_concepts: 9 },
    });
    expect(text('stats.brokenLinks|{"count":2}')).toBeTruthy();
    expect(text('stats.invalidPageTypes|{"count":3}')).toBeTruthy();
    expect(text('stats.provenanceGaps|{"count":4}')).toBeTruthy();
  });

  it('shows only the kinds of issue that exist', () => {
    renderBadges({
      structural_issues: { broken_links: 0, invalid_frontmatter_types: 3, provenance_gaps: 0, scanned_concepts: 9 },
    });
    expect(screen.queryByText(/^stats\.brokenLinks/)).toBeNull();
    expect(text('stats.invalidPageTypes|{"count":3}')).toBeTruthy();
    expect(screen.queryByText(/^stats\.provenanceGaps/)).toBeNull();
  });

  it('shows indexed assets when there are asset files, and failed ones when any failed', () => {
    renderBadges({ asset_index: { indexed: 5, pending: 0, failed: 2, total_files: 8, enabled: true } });
    expect(text('stats.indexedAssets|{"count":5}')).toBeTruthy();
    expect(text('stats.failedAssets|{"count":2}')).toBeTruthy();
  });

  it('hides indexed assets without asset files, but still reports failed ones', () => {
    renderBadges({ asset_index: { indexed: 0, pending: 0, failed: 1, total_files: 0, enabled: true } });
    expect(screen.queryByText(/^stats\.indexedAssets/)).toBeNull();
    expect(text('stats.failedAssets|{"count":1}')).toBeTruthy();
  });

  it('hides failed assets when none failed', () => {
    renderBadges({ asset_index: { indexed: 3, pending: 0, failed: 0, total_files: 3, enabled: true } });
    expect(screen.queryByText(/^stats\.failedAssets/)).toBeNull();
  });

  it('shows no asset badge or hint for a vault without an asset index', () => {
    renderBadges({ asset_index: undefined });
    expect(screen.queryByText(/^stats\.(indexedAssets|failedAssets)/)).toBeNull();
    expect(text('stats.assetsVisionHint')).toBeNull();
  });
});

describe('WikiStatsBadges: review shortcuts', () => {
  it('hides the shortcuts when nothing waits for review', () => {
    renderBadges();
    expect(screen.queryByRole('button')).toBeNull();
  });

  it('opens the synthesis review from the pending badge', async () => {
    const { onOpenSynthesisPending, onOpenDuplicateReview } = renderBadges({}, { synthesisPendingCount: 4 });
    await click(screen.getByRole('button', { name: 'stats.synthesisPending|{"count":4}' }));
    expect(onOpenSynthesisPending).toHaveBeenCalledOnce();
    expect(onOpenDuplicateReview).not.toHaveBeenCalled();
  });

  it.each([
    [false, 'bg-amber-500/10'],
    [true, 'bg-rose-500/10'],
  ])(
    'opens the duplicate review from the badge, which is emphasised when it blocks compile (%s)',
    async (blocks, tone) => {
      const { onOpenSynthesisPending, onOpenDuplicateReview } = renderBadges(
        {},
        { duplicateGroupsPending: 2, dedupBlocksCompile: blocks },
      );
      const badge = screen.getByRole('button', { name: 'stats.duplicateGroupsPending|{"count":2}' });
      expect(badge.className).toContain(tone);
      await click(badge);
      expect(onOpenDuplicateReview).toHaveBeenCalledOnce();
      expect(onOpenSynthesisPending).not.toHaveBeenCalled();
    },
  );
});

describe('WikiStatsBadges: last maintenance', () => {
  const ranAt = '2026-03-04T05:06:07Z';
  const maintained = (over: Partial<NonNullable<WikiStats['maintain_state']>> = {}): Partial<WikiStats> => ({
    maintain_state: {
      last_run_at: ranAt,
      last_mode: 'full',
      last_issues_found: 0,
      last_issues_fixed: 0,
      last_connections_discovered: 0,
      last_duration_ms: 0,
      last_skipped_reason: null,
      ...over,
    },
  });

  it('says maintenance never ran when there is no run time', () => {
    renderBadges({ maintain_state: undefined });
    expect(text('stats.lastMaintainNever')).toBeTruthy();
    expect(screen.queryByText(/^stats\.lastMaintain\|/)).toBeNull();
  });

  it.each(['en', 'ja'])('says when the last maintenance ran, in the %s locale', (locale) => {
    world.locale = locale;
    renderBadges(maintained());
    const time = formatCognitiveUpdatedAt(ranAt, locale);
    expect(text(`stats.lastMaintain|${JSON.stringify({ time })}`)).toBeTruthy();
    expect(text('stats.lastMaintainNever')).toBeNull();
  });

  it.each([
    ['compile_in_progress', 'stats.lastMaintainSkippedCompile'],
    ['anything_else', 'stats.lastMaintainSkipped'],
  ])('explains a skipped run (%s) instead of giving its time', (reason, label) => {
    renderBadges(maintained({ last_skipped_reason: reason, last_issues_found: 3 }));
    expect(text(label)).toBeTruthy();
    expect(screen.queryByText(/^stats\.lastMaintain\|/)).toBeNull();
    expect(screen.queryByText(/^stats\.lastMaintainSummary/)).toBeNull();
  });

  it.each([
    [{ last_issues_found: 5, last_issues_fixed: 0 }, '{"fixed":0,"found":5}'],
    [{ last_issues_found: 0, last_issues_fixed: 2 }, '{"fixed":2,"found":0}'],
    [{ last_issues_found: 5, last_issues_fixed: 3 }, '{"fixed":3,"found":5}'],
  ])('summarises a run that found or fixed something (%j)', (over, values) => {
    renderBadges(maintained(over));
    expect(text(`stats.lastMaintainSummary|${values}`)).toBeTruthy();
  });

  it('gives no summary for a run that found and fixed nothing', () => {
    renderBadges(maintained());
    expect(screen.queryByText(/^stats\.lastMaintainSummary/)).toBeNull();
  });

  it('gives no summary when maintenance never ran', () => {
    renderBadges({ maintain_state: undefined });
    expect(screen.queryByText(/^stats\.lastMaintainSummary/)).toBeNull();
  });
});

describe('WikiStatsBadges: hints', () => {
  it.each([
    [{ total_files: 4, enabled: false }, true],
    [{ total_files: 4, enabled: true }, false],
    [{ total_files: 0, enabled: false }, false],
  ])('hints at enabling vision for assets %j: %s', (asset, shown) => {
    renderBadges({ asset_index: { indexed: 0, pending: 0, failed: 0, ...asset } });
    expect(Boolean(text('stats.assetsVisionHint'))).toBe(shown);
  });

  const issues = (over: Partial<NonNullable<WikiStats['structural_issues']>>): Partial<WikiStats> => ({
    structural_issues: {
      broken_links: 0,
      invalid_frontmatter_types: 0,
      provenance_gaps: 0,
      scanned_concepts: 9,
      ...over,
    },
  });

  it.each([
    ['broken links', { broken_links: 1 }],
    ['invalid page types', { invalid_frontmatter_types: 1 }],
    ['provenance gaps', { provenance_gaps: 1 }],
  ])('points to the health report when there are %s and no report yet', (_label, over) => {
    renderBadges(issues(over));
    expect(text('stats.structuralHint')).toBeTruthy();
  });

  it('does not point to the health report for a clean vault', () => {
    renderBadges(issues({}));
    expect(text('stats.structuralHint')).toBeNull();
  });

  it.each([
    ['a report exists', { healthReport: healthOf() }],
    ['the report is loading', { isLoadingHealthReport: true }],
    ['the report failed to load', { healthReportLoadError: true }],
  ])('does not point to the health report once %s', (_label, over) => {
    renderBadges(issues({ broken_links: 1 }), over);
    expect(text('stats.structuralHint')).toBeNull();
  });
});
