/**
 * [INPUT] Unified skill growth audit data from API
 * [OUTPUT] Rendered dashboard for negative growth outcomes
 * [POS] myrm-agent-frontend/src/components/settings/EvolutionRejectionDashboard.tsx
 */
'use client';

import React, { useCallback, useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Activity, AlertTriangle, Clock, Loader2, RefreshCw, ShieldX, TrendingDown } from 'lucide-react';
import { IconGlow } from '@/components/features/icons/PremiumIcons';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/primitives/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/primitives/table';
import { cn } from '@/lib/utils/classnameUtils';
import { localizeReactNode, selectLocalizedText } from '@/lib/utils/localeText';
import {
  getSkillGrowthAuditStats,
  listSkillGrowthAudit,
  type SkillGrowthAuditEntry,
  type SkillGrowthStatus,
  type SkillGrowthAuditStats,
} from '@/services/skill-growth';
import { toast } from 'sonner';

const STATUS_TONE: Record<
  SkillGrowthStatus,
  { badgeClassName: string; icon: React.ComponentType<{ className?: string }>; labelKey: string }
> = {
  PENDING_REVIEW: {
    badgeClassName: 'border-amber-300/40 bg-amber-500/10 text-amber-600',
    icon: Clock,
    labelKey: 'status.pendingReview',
  },
  AUTO_APPLIED: {
    badgeClassName: 'border-emerald-300/40 bg-emerald-500/10 text-emerald-600',
    icon: IconGlow,
    labelKey: 'status.autoApplied',
  },
  FAILED_SCAN: {
    badgeClassName: 'border-rose-300/40 bg-rose-500/10 text-rose-600',
    icon: AlertTriangle,
    labelKey: 'status.failedScan',
  },
  BLOCKED_LOCKED: {
    badgeClassName: 'border-orange-300/40 bg-orange-500/10 text-orange-600',
    icon: ShieldX,
    labelKey: 'status.blockedLocked',
  },
  APPROVED: {
    badgeClassName: 'border-sky-300/40 bg-sky-500/10 text-sky-600',
    icon: Activity,
    labelKey: 'status.approved',
  },
  REJECTED: {
    badgeClassName: 'border-red-300/40 bg-red-500/10 text-red-600',
    icon: ShieldX,
    labelKey: 'status.rejected',
  },
  APPLY_FAILED: {
    badgeClassName: 'border-orange-300/40 bg-orange-500/10 text-orange-600',
    icon: AlertTriangle,
    labelKey: 'status.applyFailed',
  },
};

export function EvolutionRejectionDashboard() {
  const t = useTranslations('settingsTabs.evolutionRejection');
  const locale = useLocale();
  const text = useCallback((value: string) => selectLocalizedText(value, locale), [locale]);

  const [entries, setEntries] = useState<SkillGrowthAuditEntry[]>([]);
  const [stats, setStats] = useState<SkillGrowthAuditStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [statsLoading, setStatsLoading] = useState(true);
  const [timeRange, setTimeRange] = useState(30);
  const [retryingIds, setRetryingIds] = useState<Set<string>>(new Set());

  const fetchEntries = useCallback(async () => {
    setLoading(true);
    try {
      setEntries(await listSkillGrowthAudit(20, timeRange));
    } catch (error) {
      toast.error(text('加载技能成长审计失败 / Failed to fetch skill growth audit'));
      console.error(error);
    } finally {
      setLoading(false);
    }
  }, [text, timeRange]);

  const fetchStats = useCallback(async () => {
    setStatsLoading(true);
    try {
      setStats(await getSkillGrowthAuditStats(timeRange));
    } catch (error) {
      toast.error(text('加载技能成长审计统计失败 / Failed to fetch skill growth audit stats'));
      console.error(error);
    } finally {
      setStatsLoading(false);
    }
  }, [text, timeRange]);

  useEffect(() => {
    void fetchEntries();
    void fetchStats();

    let timeoutId: NodeJS.Timeout;
    const handleSseEvent = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => {
        void fetchEntries();
        void fetchStats();
      }, 1000);
    };
    window.addEventListener('skill_growth_updated', handleSseEvent);
    window.addEventListener('app_resync_required', handleSseEvent);
    return () => {
      window.removeEventListener('skill_growth_updated', handleSseEvent);
      window.removeEventListener('app_resync_required', handleSseEvent);
      clearTimeout(timeoutId);
    };
  }, [fetchEntries, fetchStats]);

  const formatTime = (timestamp: string): string => new Date(timestamp).toLocaleString();

  const renderStatusBadge = (status: SkillGrowthStatus) => {
    const config = STATUS_TONE[status];
    const Icon = config.icon;
    return (
      <Badge variant="outline" className={cn('gap-1 border', config.badgeClassName)}>
        <Icon className="h-3 w-3" />
        {t(config.labelKey as Parameters<typeof t>[0])}
      </Badge>
    );
  };

  return localizeReactNode(
    <div className="animate-in slide-in-from-bottom-4 space-y-6 fade-in duration-500">
      <div className="flex flex-col gap-2">
        <h2 className="text-2xl font-semibold tracking-tight">{t('title')}</h2>
        <p className="text-sm text-muted-foreground">{t('description')}</p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card className="border-border/50 bg-gradient-to-br from-card to-card/50 transition-all hover:shadow-md">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <div className="rounded-full bg-red-500/10 p-1.5 text-red-500">
                <ShieldX className="h-4 w-4" />
              </div>
              {t('totalEvents')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="flex h-9 items-center">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <div className="text-3xl font-bold tracking-tight">{stats?.totalEvents ?? 0}</div>
            )}
            <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
              <Clock className="h-3 w-3" />
              {t('lastDays', { days: timeRange })}
            </p>
          </CardContent>
        </Card>

        <Card className="border-border/50 bg-gradient-to-br from-card to-card/50 transition-all hover:shadow-md">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <div className="rounded-full bg-blue-500/10 p-1.5 text-blue-500">
                <TrendingDown className="h-4 w-4" />
              </div>
              {t('avgConfidence')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="flex h-9 items-center">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <div className="text-3xl font-bold tracking-tight">{stats?.avgConfidence?.toFixed(2) ?? '0.00'}</div>
            )}
            <p className="mt-2 flex items-center gap-1 text-xs text-muted-foreground">
              <Activity className="h-3 w-3" />
              {t('avgConfidenceHint')}
            </p>
          </CardContent>
        </Card>

        <Card className="border-border/50 bg-gradient-to-br from-card to-card/50 transition-all hover:shadow-md">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
              <div className="rounded-full bg-primary/10 p-1.5 text-primary">
                <Clock className="h-4 w-4" />
              </div>
              {t('timeRange')}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <div className="mt-1 flex h-9 items-center">
              <select
                className={cn(
                  'w-full cursor-pointer rounded-lg border border-border/50 bg-accent/50 px-3 py-2 text-sm font-medium text-foreground',
                  'transition-all duration-200 hover:bg-accent/80 focus:outline-none focus:ring-2 focus:ring-primary/20',
                )}
                value={timeRange}
                onChange={(event) => setTimeRange(Number(event.target.value))}
              >
                <option value={7}>7 {t('days')}</option>
                <option value={30}>30 {t('days')}</option>
                <option value={90}>90 {t('days')}</option>
                <option value={180}>180 {t('days')}</option>
              </select>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">{t('selectAnalysisPeriod')}</p>
          </CardContent>
        </Card>
      </div>

      {stats && stats.byStatus.length > 0 && (
        <Card className="border-border/50">
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-sm font-medium">
              <Activity className="h-4 w-4 text-muted-foreground" />
              {t('statusDistribution')}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {stats.byStatus.map((bucket) => (
              <div key={bucket.key} className="space-y-1.5">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="font-medium">{t(`status.${bucket.key}` as Parameters<typeof t>[0])}</span>
                  <span className="text-muted-foreground">
                    {bucket.count} · {bucket.percentage.toFixed(1)}%
                  </span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div
                    className="h-full rounded-full bg-primary/70 transition-all"
                    style={{ width: `${Math.min(bucket.percentage, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      <Card className="border-border/50">
        <CardHeader className="flex flex-row items-center justify-between gap-3 pb-3">
          <div>
            <CardTitle className="text-sm font-medium">{t('latestEvents')}</CardTitle>
            <p className="mt-1 text-xs text-muted-foreground">{t('latestEventsDescription')}</p>
          </div>
          <Button variant="outline" size="sm" onClick={() => void Promise.all([fetchEntries(), fetchStats()])}>
            <RefreshCw className="mr-2 h-4 w-4" />
            {t('refresh')}
          </Button>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12 text-sm text-muted-foreground">
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              {t('loading')}
            </div>
          ) : entries.length === 0 ? (
            <div className="py-12 text-center">
              <ShieldX className="mx-auto mb-3 h-10 w-10 text-muted-foreground/40" />
              <p className="text-sm font-medium text-foreground">{t('noLogs')}</p>
              <p className="mt-1 text-xs text-muted-foreground">{t('noLogsDesc')}</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t('skill')}</TableHead>
                    <TableHead>{t('statusColumn')}</TableHead>
                    <TableHead>{t('growthType')}</TableHead>
                    <TableHead>{t('reason')}</TableHead>
                    <TableHead>{t('confidence')}</TableHead>
                    <TableHead>{t('time')}</TableHead>
                    <TableHead className="text-right">{t('actions')}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {entries.map((entry) => (
                    <TableRow key={entry.eventId}>
                      <TableCell className="min-w-[180px]">
                        <div className="flex flex-col gap-1">
                          <span className="font-medium text-foreground">{entry.skillName}</span>
                          <span className="text-xs text-muted-foreground">
                            {entry.source === 'draft' ? t('sourceDraft') : t('sourceEvolution')}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>{renderStatusBadge(entry.status)}</TableCell>
                      <TableCell className="text-sm text-muted-foreground">{entry.growthType}</TableCell>
                      <TableCell className="max-w-[400px] text-sm text-muted-foreground">
                        <div className="space-y-2">
                          {(() => {
                            const reason = entry.reason || '';
                            const codeBlockMatch = reason.match(/```(?:python)?\n([\s\S]*?)\n```/);
                            if (codeBlockMatch) {
                              const textPart = reason.replace(codeBlockMatch[0], '').trim();
                              return (
                                <>
                                  <p className="line-clamp-2 text-foreground font-medium">{textPart}</p>
                                  <pre className="mt-1 max-h-[80px] overflow-hidden rounded bg-red-950/20 px-2 py-1 text-xs text-red-400 border border-red-900/30">
                                    <code>{codeBlockMatch[1].trim()}</code>
                                  </pre>
                                </>
                              );
                            }
                            return <p className="line-clamp-3">{reason}</p>;
                          })()}
                          {entry.reasonCode && (
                            <p className="text-xs text-muted-foreground/80">
                              {t('reasonCode')}: {entry.reasonCode}
                            </p>
                          )}
                          {entry.remediation && (
                            <p className="line-clamp-2 text-xs text-muted-foreground/80">{entry.remediation}</p>
                          )}
                        </div>
                      </TableCell>
                      <TableCell className="text-sm">
                        {entry.confidence !== null ? entry.confidence.toFixed(2) : '—'}
                      </TableCell>
                      <TableCell className="text-sm text-muted-foreground">{formatTime(entry.createdAt)}</TableCell>
                      <TableCell className="text-right">
                        {(entry.status === 'REJECTED' || entry.status === 'BLOCKED_LOCKED') && (
                          <Button
                            variant="outline"
                            size="sm"
                            disabled={retryingIds.has(entry.eventId)}
                            onClick={async () => {
                              setRetryingIds((prev) => new Set(prev).add(entry.eventId));
                              try {
                                const res = await fetch(
                                  `/api/skills/evolution/fix/${entry.skillId || entry.skillName}`,
                                  {
                                    method: 'POST',
                                    headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify({ reason: entry.reason, force_retry: true }),
                                  },
                                );
                                if (!res.ok) throw new Error('Failed to force retry');
                                toast.success(text('已强制重试 / Force retry started'));

                                // Optimistic UI update: instantly change status to PENDING_REVIEW
                                setEntries((prev) =>
                                  prev.map((e) =>
                                    e.eventId === entry.eventId
                                      ? { ...e, status: 'PENDING_REVIEW' as SkillGrowthStatus }
                                      : e,
                                  ),
                                );
                              } catch {
                                toast.error(text('重试失败 / Retry failed'));
                              } finally {
                                setRetryingIds((prev) => {
                                  const next = new Set(prev);
                                  next.delete(entry.eventId);
                                  return next;
                                });
                              }
                            }}
                          >
                            {retryingIds.has(entry.eventId) ? (
                              <>
                                <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                                {text('重试中... / Retrying...')}
                              </>
                            ) : (
                              t('forceRetry')
                            )}
                          </Button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>,
    locale,
  );
}
