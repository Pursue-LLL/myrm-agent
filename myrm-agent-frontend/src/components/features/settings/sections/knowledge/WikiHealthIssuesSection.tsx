'use client';

import { useLocale, useTranslations } from 'next-intl';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import type { WikiHealthIssue, WikiHealthReport } from '@/services/wikiService';
import { WikiGovernanceWorkbench } from './wiki/WikiGovernanceWorkbench';

interface WikiHealthIssuesSectionProps {
  report: WikiHealthReport | null;
  isLoading?: boolean;
  loadError?: boolean;
  expanded: boolean;
  onToggleExpanded: () => void;
  onRecompile: () => void;
  isRecompiling?: boolean;
  onRepair: () => void;
  isRepairing?: boolean;
  onNavigateIssue: (location: string) => void;
  onOpenDuplicateReview: () => void;
  onOpenPendingEdits: () => void;
  onRefresh: () => void;
}

function formatDriftCheckedAt(iso: string, locale: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short' }).format(date);
}

function severityClass(severity: string): string {
  if (severity === 'high') {
    return 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border-rose-500/30';
  }
  if (severity === 'medium') {
    return 'bg-amber-500/10 text-amber-700 dark:text-amber-300 border-amber-500/30';
  }
  return 'bg-sky-500/10 text-sky-700 dark:text-sky-300 border-sky-500/30';
}

function issueTypeLabel(
  issueType: string,
  t: ReturnType<typeof useTranslations<'settings.wiki.healthReport'>>,
): string {
  const known = [
    'broken_link',
    'broken_wikilink',
    'invalid_frontmatter_type',
    'stale',
    'drift',
    'incomplete',
    'knowledge_gap',
    'provenance_gap',
    'security_redacted',
    'security_removed',
  ] as const;
  if ((known as readonly string[]).includes(issueType)) {
    return t(`issueType.${issueType}` as `issueType.${(typeof known)[number]}`);
  }
  return issueType;
}

function locationLabel(location: string): string {
  const normalized = location.replace(/\\/g, '/');
  const parts = normalized.split('/');
  return parts.length > 0 ? parts[parts.length - 1] : location;
}

export function WikiHealthIssuesSection({
  report,
  isLoading = false,
  loadError = false,
  expanded,
  onToggleExpanded,
  onRecompile,
  isRecompiling = false,
  onRepair,
  isRepairing = false,
  onNavigateIssue,
  onOpenDuplicateReview,
  onOpenPendingEdits,
  onRefresh,
}: WikiHealthIssuesSectionProps) {
  const t = useTranslations('settings.wiki.healthReport');
  const locale = useLocale();

  if (isLoading) {
    return (
      <div
        className="rounded-lg border border-border/60 bg-muted/20 p-4 text-sm text-muted-foreground"
        data-testid="wiki-health-section"
        data-state="loading"
      >
        {t('loading')}
      </div>
    );
  }

  if (loadError) {
    return (
      <div
        className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-4 space-y-2"
        data-testid="wiki-health-section"
        data-state="error"
      >
        <p className="text-sm text-rose-800 dark:text-rose-200">{t('loadFailed')}</p>
        <Button type="button" variant="outline" size="sm" onClick={onRefresh}>
          {t('retry')}
        </Button>
      </div>
    );
  }

  if (!report) {
    return null;
  }

  const openCount = report.open_actions_count;
  const hasIssues = report.issues.length > 0;
  const showCrossLinks = report.duplicate_groups_pending > 0 || report.synthesis_pending > 0;
  const isTruncated = report.issues_found > report.issues.length;

  if (openCount === 0 && !showCrossLinks && !hasIssues) {
    return (
      <div
        className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4 space-y-1"
        data-testid="wiki-health-section"
        data-state="clear"
      >
        <p className="text-sm text-emerald-800 dark:text-emerald-200">{t('allClear')}</p>
        <p className="text-xs text-muted-foreground">{t('structuralScopeHint')}</p>
      </div>
    );
  }

  return (
    <div
      className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 space-y-3"
      data-testid="wiki-health-section"
      data-state="issues"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="space-y-1">
          <div className="text-sm font-medium text-foreground">{t('title')}</div>
          <p className="text-xs text-muted-foreground">
            {t('summary', { open: openCount, total: report.issues_found })}
          </p>
          <p className="text-xs text-muted-foreground">{t('structuralScopeHint')}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button type="button" variant="ghost" size="sm" onClick={onRefresh}>
            {t('refresh')}
          </Button>
          {hasIssues ? (
            <Button type="button" variant="ghost" size="sm" onClick={onToggleExpanded}>
              {expanded ? (
                <>
                  <ChevronUp className="mr-1 h-4 w-4" />
                  {t('collapse')}
                </>
              ) : (
                <>
                  <ChevronDown className="mr-1 h-4 w-4" />
                  {t('expand')}
                </>
              )}
            </Button>
          ) : null}
        </div>
      </div>

      {isTruncated ? (
        <p className="text-xs text-muted-foreground">
          {t('truncatedList', { shown: report.issues.length, total: report.issues_found })}
        </p>
      ) : null}

      {showCrossLinks ? (
        <div className="flex flex-wrap gap-2">
          {report.duplicate_groups_pending > 0 ? (
            <Button type="button" variant="outline" size="sm" onClick={onOpenDuplicateReview}>
              {t('reviewDuplicates', { count: report.duplicate_groups_pending })}
            </Button>
          ) : null}
          {report.synthesis_pending > 0 ? (
            <Button type="button" variant="outline" size="sm" onClick={onOpenPendingEdits}>
              {t('reviewPending', { count: report.synthesis_pending })}
            </Button>
          ) : null}
        </div>
      ) : null}

      <WikiGovernanceWorkbench onOpenPendingEdits={onOpenPendingEdits} onRefreshParent={onRefresh} />

      {expanded && hasIssues ? (
        <ul className="max-h-72 space-y-2 overflow-y-auto">
          {report.issues.map((issue, index) => (
            <HealthIssueRow
              key={`${issue.issue_type}-${issue.location}-${index}`}
              issue={issue}
              onRecompile={onRecompile}
              isRecompiling={isRecompiling}
              onRepair={onRepair}
              isRepairing={isRepairing}
              onNavigateIssue={onNavigateIssue}
            />
          ))}
        </ul>
      ) : null}

      {report.drift_sampled ? (
        <div className="space-y-1">
          <p className="text-xs text-muted-foreground">{t('driftSampleHint')}</p>
          {report.drift_checked_at ? (
            <p className="text-xs text-muted-foreground">
              {t('lastDriftCheck', {
                checkedAt: formatDriftCheckedAt(report.drift_checked_at, locale),
              })}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function HealthIssueRow({
  issue,
  onRecompile,
  isRecompiling,
  onRepair,
  isRepairing,
  onNavigateIssue,
}: {
  issue: WikiHealthIssue;
  onRecompile: () => void;
  isRecompiling: boolean;
  onRepair: () => void;
  isRepairing: boolean;
  onNavigateIssue: (location: string) => void;
}) {
  const t = useTranslations('settings.wiki.healthReport');

  const actionLabel =
    issue.action_kind === 'recompile'
      ? t('actionRecompile')
      : issue.action_kind === 'repair'
        ? t('actionRepair')
        : issue.action_kind === 'navigate'
          ? t('actionOpen')
          : null;

  const onAction =
    issue.action_kind === 'recompile'
      ? onRecompile
      : issue.action_kind === 'repair' && issue.issue_type === 'invalid_frontmatter_type'
        ? onRepair
        : issue.action_kind === 'repair' || issue.action_kind === 'navigate'
          ? () => onNavigateIssue(issue.location)
          : undefined;

  const actionDisabled =
    (issue.action_kind === 'recompile' && isRecompiling) ||
    (issue.action_kind === 'repair' && issue.issue_type === 'invalid_frontmatter_type' && isRepairing);

  return (
    <li className="rounded-md border border-border/60 bg-background/80 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className={severityClass(issue.severity)}>
              {issueTypeLabel(issue.issue_type, t)}
            </Badge>
            <span className="truncate text-xs font-mono text-muted-foreground">{locationLabel(issue.location)}</span>
          </div>
          <p className="text-sm text-foreground">{issue.description}</p>
          {issue.suggested_fix ? <p className="text-xs text-muted-foreground">{issue.suggested_fix}</p> : null}
        </div>
        {actionLabel && onAction ? (
          <Button type="button" size="sm" variant="outline" disabled={actionDisabled} onClick={onAction}>
            {actionLabel}
          </Button>
        ) : null}
      </div>
    </li>
  );
}
