'use client';

import { useTranslations } from 'next-intl';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import type { WikiHealthIssue, WikiHealthReport } from '@/services/wikiService';

interface WikiHealthIssuesSectionProps {
  report: WikiHealthReport | null;
  isLoading?: boolean;
  expanded: boolean;
  onToggleExpanded: () => void;
  onRecompile: () => void;
  isRecompiling?: boolean;
  onOpenDuplicateReview: () => void;
  onOpenConcepts: () => void;
  onOpenPendingEdits: () => void;
  onRefresh: () => void;
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
  expanded,
  onToggleExpanded,
  onRecompile,
  isRecompiling = false,
  onOpenDuplicateReview,
  onOpenConcepts,
  onOpenPendingEdits,
  onRefresh,
}: WikiHealthIssuesSectionProps) {
  const t = useTranslations('settings.wiki.healthReport');

  if (isLoading) {
    return (
      <div className="rounded-lg border border-border/60 bg-muted/20 p-4 text-sm text-muted-foreground">
        {t('loading')}
      </div>
    );
  }

  if (!report) {
    return null;
  }

  const openCount = report.open_actions_count;
  const hasIssues = report.issues.length > 0;
  const showCrossLinks =
    report.duplicate_groups_pending > 0 || report.synthesis_pending > 0;

  if (openCount === 0 && !showCrossLinks && !hasIssues) {
    return (
      <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-4 text-sm text-emerald-800 dark:text-emerald-200">
        {t('allClear')}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="space-y-1">
          <div className="text-sm font-medium text-foreground">{t('title')}</div>
          <p className="text-xs text-muted-foreground">
            {t('summary', { open: openCount, total: report.issues_found })}
          </p>
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

      {expanded && hasIssues ? (
        <ul className="max-h-72 space-y-2 overflow-y-auto">
          {report.issues.map((issue, index) => (
            <HealthIssueRow
              key={`${issue.issue_type}-${issue.location}-${index}`}
              issue={issue}
              onRecompile={onRecompile}
              isRecompiling={isRecompiling}
              onOpenConcepts={onOpenConcepts}
            />
          ))}
        </ul>
      ) : null}

      {report.drift_sampled ? (
        <p className="text-xs text-muted-foreground">{t('driftSampleHint')}</p>
      ) : null}
    </div>
  );
}

function HealthIssueRow({
  issue,
  onRecompile,
  isRecompiling,
  onOpenConcepts,
}: {
  issue: WikiHealthIssue;
  onRecompile: () => void;
  isRecompiling: boolean;
  onOpenConcepts: () => void;
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
      : issue.action_kind === 'repair' || issue.action_kind === 'navigate'
        ? onOpenConcepts
        : undefined;

  return (
    <li className="rounded-md border border-border/60 bg-background/80 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0 flex-1 space-y-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className={severityClass(issue.severity)}>
              {issueTypeLabel(issue.issue_type, t)}
            </Badge>
            <span className="truncate text-xs font-mono text-muted-foreground">
              {locationLabel(issue.location)}
            </span>
          </div>
          <p className="text-sm text-foreground">{issue.description}</p>
          {issue.suggested_fix ? (
            <p className="text-xs text-muted-foreground">{issue.suggested_fix}</p>
          ) : null}
        </div>
        {actionLabel && onAction ? (
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={issue.action_kind === 'recompile' && isRecompiling}
            onClick={onAction}
          >
            {actionLabel}
          </Button>
        ) : null}
      </div>
    </li>
  );
}
