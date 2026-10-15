'use client';

import type { WikiHealthReport, WikiMaintainProgress, WikiMaintainResponse } from '@/services/wikiService';

/**
 * [INPUT] comma-separated tag/alias input strings; WikiMaintainResponse and WikiMaintainProgress from wikiService
 * [OUTPUT] splitTagsInput; resolveHealthIssueNavigationTarget; healthReportFromMaintainResponse; resolveMaintainToast;
 *          resolveMaintainProgressLabel; resolveMaintainFailureToastKey
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

export type MaintainToastKey =
  | 'success.maintainRemovedSensitive'
  | 'success.maintainCancelled'
  | 'errors.maintainAiUnavailable'
  | 'healthReport.maintainToastOpen'
  | 'success.maintainSummaryWithLinks'
  | 'success.maintainSummary'
  | 'success.maintainComplete';

export interface MaintainToast {
  variant: 'success' | 'message' | 'warning';
  /** Key under the `settings.wiki` translation namespace. */
  key: MaintainToastKey;
  values?: Record<string, string | number>;
}

const REMOVED_PATHS_MAX_CHARS = 120;

/** Pick the one toast that summarises a maintenance run; the order is what the user needs to see first. */
export function resolveMaintainToast(result: WikiMaintainResponse, cancelled = false): MaintainToast {
  const removed = result.raw_security_removed ?? 0;
  if (removed > 0) {
    const joined = (result.raw_security_removed_paths ?? []).join(', ');
    const paths =
      joined.length > REMOVED_PATHS_MAX_CHARS ? `${joined.slice(0, REMOVED_PATHS_MAX_CHARS - 3)}...` : joined;
    return { variant: 'success', key: 'success.maintainRemovedSensitive', values: { count: removed, paths } };
  }
  if (cancelled) {
    return { variant: 'message', key: 'success.maintainCancelled' };
  }
  if (result.ai_unavailable) {
    return { variant: 'warning', key: 'errors.maintainAiUnavailable' };
  }

  const fixed = result.issues_fixed ?? 0;
  const openActions = result.open_actions_count ?? 0;
  if (openActions > 0) {
    return { variant: 'message', key: 'healthReport.maintainToastOpen', values: { open: openActions, fixed } };
  }
  if (result.connections_discovered > 0) {
    return {
      variant: 'success',
      key: 'success.maintainSummaryWithLinks',
      values: { found: result.issues_found, fixed, connections: result.connections_discovered },
    };
  }
  if (fixed > 0) {
    return { variant: 'success', key: 'success.maintainSummary', values: { found: result.issues_found, fixed } };
  }
  return { variant: 'success', key: 'success.maintainComplete' };
}

export interface MaintainProgressLabel {
  /** Key under the `settings.wiki` translation namespace. */
  key: 'maintainProgress.driftReview' | 'maintainProgress.linkDiscovery';
  values: { done: number; total: number };
}

/** The button text of a run that is inside a model phase; null before the first phase starts. */
export function resolveMaintainProgressLabel(progress: WikiMaintainProgress | null): MaintainProgressLabel | null {
  if (!progress) {
    return null;
  }
  return {
    key: progress.phase === 'drift_review' ? 'maintainProgress.driftReview' : 'maintainProgress.linkDiscovery',
    values: { done: progress.done, total: progress.total },
  };
}

export type MaintainFailureReason = 'compile_busy' | 'failed';

/** Key under the `settings.wiki` translation namespace for a run that did not finish. */
export function resolveMaintainFailureToastKey(
  reason: MaintainFailureReason,
): 'errors.maintainCompileBusy' | 'errors.maintainFailed' {
  return reason === 'compile_busy' ? 'errors.maintainCompileBusy' : 'errors.maintainFailed';
}

/** Build Overview health report state from a finished maintenance run (preserves full-mode drift). */
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
