import { readFileSync } from 'node:fs';
import path from 'node:path';

import { describe, expect, it } from 'vitest';

import { locales } from '@/i18n/config';
import type { WikiMaintainResponse } from '@/services/wikiService';

import {
  healthReportFromMaintainResponse,
  resolveHealthIssueNavigationTarget,
  resolveMaintainFailureToastKey,
  resolveMaintainProgressLabel,
  resolveMaintainToast,
} from '../wikiSectionUtils';

function maintainResponse(overrides: Partial<WikiMaintainResponse> = {}): WikiMaintainResponse {
  return {
    issues_found: 0,
    issues_fixed: 0,
    connections_discovered: 0,
    duration_ms: 1,
    open_actions_count: 0,
    raw_security_removed: 0,
    raw_security_removed_paths: [],
    issues: [],
    ...overrides,
  };
}

const LOCALES_DIR = path.join(process.cwd(), 'locales');

type MessageTree = { [key: string]: string | MessageTree };

function lookupWikiMessage(tree: MessageTree, key: string): string | undefined {
  let node: string | MessageTree | undefined = (tree.settings as MessageTree).wiki;
  for (const part of key.split('.')) {
    node = typeof node === 'object' ? node[part] : undefined;
  }
  return typeof node === 'string' ? node : undefined;
}

/** ICU argument names: `{name}` and the head of `{name, plural, ...}`; `#` and nested branch text do not match. */
function icuArguments(message: string): string[] {
  return [...new Set([...message.matchAll(/\{(\w+)\s*[,}]/g)].map((match) => match[1] as string))].sort();
}

describe('resolveMaintainToast locale contract', () => {
  const outcomes: WikiMaintainResponse[] = [
    maintainResponse({ raw_security_removed: 1, raw_security_removed_paths: ['a.md'] }),
    maintainResponse({ open_actions_count: 1 }),
    maintainResponse({ connections_discovered: 1 }),
    maintainResponse({ issues_fixed: 1 }),
    maintainResponse(),
  ];

  it.each(locales)('%s has every toast message with exactly the arguments the resolver supplies', (code) => {
    const tree = JSON.parse(readFileSync(path.join(LOCALES_DIR, `${code}.json`), 'utf8')) as MessageTree;

    for (const result of outcomes) {
      const toast = resolveMaintainToast(result);
      const message = lookupWikiMessage(tree, toast.key);

      expect(message, `${code}: ${toast.key}`).toBeTypeOf('string');
      expect(icuArguments(message as string), `${code}: ${toast.key}`).toEqual(Object.keys(toast.values ?? {}).sort());
    }
  });
});

describe('resolveMaintainToast', () => {
  it('reports removed sensitive raw files first, with the paths joined', () => {
    expect(
      resolveMaintainToast(
        maintainResponse({
          raw_security_removed: 2,
          raw_security_removed_paths: ['inbox/a.md', 'inbox/b.md'],
          open_actions_count: 3,
          connections_discovered: 4,
        }),
      ),
    ).toEqual({
      variant: 'success',
      key: 'success.maintainRemovedSensitive',
      values: { count: 2, paths: 'inbox/a.md, inbox/b.md' },
    });
  });

  it('truncates a long removed-paths list to 120 characters', () => {
    const toast = resolveMaintainToast(
      maintainResponse({ raw_security_removed: 1, raw_security_removed_paths: ['x'.repeat(200)] }),
    );

    expect(toast.values?.paths).toBe(`${'x'.repeat(117)}...`);
  });

  it('points to the health panel when open actions remain, even if links were found', () => {
    expect(
      resolveMaintainToast(maintainResponse({ open_actions_count: 2, issues_fixed: 1, connections_discovered: 5 })),
    ).toEqual({ variant: 'message', key: 'healthReport.maintainToastOpen', values: { open: 2, fixed: 1 } });
  });

  it('reports newly discovered links together with found/fixed counts', () => {
    expect(
      resolveMaintainToast(maintainResponse({ issues_found: 3, issues_fixed: 1, connections_discovered: 4 })),
    ).toEqual({
      variant: 'success',
      key: 'success.maintainSummaryWithLinks',
      values: { found: 3, fixed: 1, connections: 4 },
    });
  });

  it('reports new links even when nothing else was found or fixed', () => {
    expect(resolveMaintainToast(maintainResponse({ connections_discovered: 2 }))).toEqual({
      variant: 'success',
      key: 'success.maintainSummaryWithLinks',
      values: { found: 0, fixed: 0, connections: 2 },
    });
  });

  it('reports fixed issues when no links were discovered', () => {
    expect(resolveMaintainToast(maintainResponse({ issues_found: 2, issues_fixed: 2 }))).toEqual({
      variant: 'success',
      key: 'success.maintainSummary',
      values: { found: 2, fixed: 2 },
    });
  });

  it('falls back to the plain completion message when nothing changed', () => {
    expect(resolveMaintainToast(maintainResponse())).toEqual({ variant: 'success', key: 'success.maintainComplete' });
  });

  it('tolerates a legacy response without the optional counters', () => {
    const legacy = {
      issues_found: 1,
      issues_fixed: 0,
      connections_discovered: 0,
      duration_ms: 1,
    } as WikiMaintainResponse;

    expect(resolveMaintainToast(legacy)).toEqual({ variant: 'success', key: 'success.maintainComplete' });
  });
});

describe('resolveMaintainProgressLabel', () => {
  it('names the phase with the pages done of total', () => {
    expect(resolveMaintainProgressLabel({ phase: 'link_discovery', done: 7, total: 20 })).toEqual({
      key: 'maintainProgress.linkDiscovery',
      values: { done: 7, total: 20 },
    });
    expect(resolveMaintainProgressLabel({ phase: 'drift_review', done: 0, total: 5 })).toEqual({
      key: 'maintainProgress.driftReview',
      values: { done: 0, total: 5 },
    });
  });

  it('has no label before the model phases start', () => {
    expect(resolveMaintainProgressLabel(null)).toBeNull();
  });

  it.each(locales)('%s words both phases with the done and total counters', (code) => {
    const tree = JSON.parse(readFileSync(path.join(LOCALES_DIR, `${code}.json`), 'utf8')) as MessageTree;

    for (const phase of ['drift_review', 'link_discovery'] as const) {
      const label = resolveMaintainProgressLabel({ phase, done: 1, total: 2 });
      const message = lookupWikiMessage(tree, label?.key ?? '');

      expect(message, `${code}: ${phase}`).toBeTypeOf('string');
      expect(icuArguments(message as string), `${code}: ${phase}`).toEqual(['done', 'total']);
    }
  });
});

describe('resolveMaintainFailureToastKey', () => {
  it('tells the user to retry after the compile when the vault is compiling', () => {
    expect(resolveMaintainFailureToastKey('compile_busy')).toBe('errors.maintainCompileBusy');
  });

  it('falls back to the generic failure for everything else', () => {
    expect(resolveMaintainFailureToastKey('failed')).toBe('errors.maintainFailed');
  });

  it.each(locales)('%s words both failure toasts', (code) => {
    const tree = JSON.parse(readFileSync(path.join(LOCALES_DIR, `${code}.json`), 'utf8')) as MessageTree;

    for (const reason of ['compile_busy', 'failed'] as const) {
      expect(lookupWikiMessage(tree, resolveMaintainFailureToastKey(reason)), `${code}: ${reason}`).toBeTypeOf(
        'string',
      );
    }
  });
});

describe('resolveHealthIssueNavigationTarget', () => {
  it('maps absolute concept paths to concept tree ids', () => {
    const target = resolveHealthIssueNavigationTarget('/vault/wiki/concepts/notes/alpha.md');
    expect(target).toEqual({ kind: 'concept', path: 'notes/alpha' });
  });

  it('maps raw-relative stale paths to raw tree ids', () => {
    const target = resolveHealthIssueNavigationTarget('inbox/draft.md');
    expect(target).toEqual({ kind: 'raw', path: 'inbox/draft.md' });
  });

  it('maps simple stale filenames to raw tree ids', () => {
    const target = resolveHealthIssueNavigationTarget('draft.md');
    expect(target).toEqual({ kind: 'raw', path: 'draft.md' });
  });

  it('maps absolute raw paths to raw highlight paths', () => {
    const target = resolveHealthIssueNavigationTarget('/vault/raw/inbox/draft.md');
    expect(target).toEqual({ kind: 'raw', path: 'inbox/draft.md' });
  });
});

describe('healthReportFromMaintainResponse', () => {
  it('preserves full-mode drift issues and marks drift_sampled', () => {
    const report = healthReportFromMaintainResponse(
      {
        issues_found: 2,
        issues_fixed: 0,
        connections_discovered: 0,
        duration_ms: 12,
        open_actions_count: 2,
        raw_security_removed: 0,
        raw_security_removed_paths: [],
        issues: [
          {
            issue_type: 'drift',
            severity: 'medium',
            location: 'notes/alpha',
            description: 'Possible drift',
            action_kind: 'navigate',
          },
          {
            issue_type: 'broken_link',
            severity: 'low',
            location: 'inbox/draft.md',
            description: 'Broken link',
            action_kind: 'navigate',
          },
        ],
      },
      'full',
      { duplicate_groups_pending: 3, synthesis_pending: 1 },
    );

    expect(report.mode).toBe('full');
    expect(report.drift_sampled).toBe(true);
    expect(report.issues).toHaveLength(2);
    expect(report.issues[0]?.issue_type).toBe('drift');
    expect(report.duplicate_groups_pending).toBe(3);
    expect(report.synthesis_pending).toBe(1);
  });

  it('uses structural mode without drift_sampled', () => {
    const report = healthReportFromMaintainResponse(
      {
        issues_found: 1,
        issues_fixed: 1,
        connections_discovered: 0,
        duration_ms: 5,
        open_actions_count: 0,
        raw_security_removed: 0,
        raw_security_removed_paths: [],
        issues: [],
      },
      'structural',
      { duplicate_groups_pending: 0, synthesis_pending: 0 },
    );

    expect(report.mode).toBe('structural');
    expect(report.drift_sampled).toBe(false);
    expect(report.open_actions_count).toBe(0);
  });
});
