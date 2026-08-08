import { describe, expect, it } from 'vitest';

import {
  healthReportFromMaintainResponse,
  resolveHealthIssueNavigationTarget,
} from '../wikiSectionUtils';

describe('resolveHealthIssueNavigationTarget', () => {
  it('maps absolute concept paths to concept tree ids', () => {
    const target = resolveHealthIssueNavigationTarget(
      '/vault/wiki/concepts/notes/alpha.md',
    );
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
