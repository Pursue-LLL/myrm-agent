'use client';

import type { WikiHealthReport, WikiMaintainResponse } from '@/services/wikiService';

/**
 * [INPUT] comma-separated tag/alias input strings; WikiMaintainResponse from wikiService
 * [OUTPUT] splitTagsInput; resolveHealthIssueNavigationTarget; healthReportFromMaintainResponse
 * [POS] Settings wiki metadata editor helpers (list parsing lives on server SSOT)
 */

export function splitTagsInput(raw: string): string[] {
  return raw
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

export type HealthIssueNavigationTarget = { kind: 'raw'; path: string } | { kind: 'concept'; path: string };

/** Map harness lint issue locations to Settings wiki navigation targets. */
export function resolveHealthIssueNavigationTarget(location: string): HealthIssueNavigationTarget {
  const normalized = location.replace(/\\/g, '/').replace(/^\//, '');

  if (normalized.includes('/concepts/') || normalized.startsWith('concepts/')) {
    const rel = normalized.includes('/concepts/')
      ? normalized.slice(normalized.indexOf('/concepts/') + '/concepts/'.length)
      : normalized.slice('concepts/'.length);
    return { kind: 'concept', path: rel.replace(/\.md$/i, '') };
  }

  if (normalized.includes('/raw/') || normalized.startsWith('raw/')) {
    const rel = normalized.includes('/raw/')
      ? normalized.slice(normalized.indexOf('/raw/') + '/raw/'.length)
      : normalized.slice('raw/'.length);
    return { kind: 'raw', path: rel };
  }

  if (normalized.endsWith('.md') || normalized.includes('/')) {
    return { kind: 'raw', path: normalized };
  }

  return { kind: 'concept', path: normalized };
}

/** Build Overview health report state from POST /wiki/maintain (preserves full-mode drift). */
export function healthReportFromMaintainResponse(
  result: WikiMaintainResponse,
  mode: 'structural' | 'full',
  crossLinks: Pick<WikiHealthReport, 'duplicate_groups_pending' | 'synthesis_pending'>,
): WikiHealthReport {
  return {
    mode,
    generated_at: new Date().toISOString(),
    open_actions_count: result.open_actions_count ?? 0,
    issues_found: result.issues_found,
    issues: result.issues ?? [],
    drift_sampled: mode === 'full' && (result.issues ?? []).some((item) => item.issue_type === 'drift'),
    drift_checked_at:
      mode === 'full' && (result.issues ?? []).some((item) => item.issue_type === 'drift')
        ? new Date().toISOString()
        : null,
    duplicate_groups_pending: crossLinks.duplicate_groups_pending,
    synthesis_pending: crossLinks.synthesis_pending,
  };
}
