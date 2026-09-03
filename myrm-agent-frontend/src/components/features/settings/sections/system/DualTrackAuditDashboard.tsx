'use client';

/**
 * [INPUT]
 * - next-intl::useTranslations (POS: i18n support)
 * - @/services/dualTrackAudit::dualTrackAuditService (POS: Audit trail & compliance stats REST client)
 * - @/components/features/icons/PremiumIcons (POS: Standard premium UI icons)
 *
 * [OUTPUT]
 * - DualTrackAuditDashboard: Settings card for dual-track prior audit logging,
 *   fail-closed pre-act/post-act alignment, rule rejection telemetry, and compliance dossier exports.
 *
 * [POS]
 * Settings -> Security Policy -> Dual-Track Prior Audit & Compliance Trail.
 */

import React, { memo, useState, useEffect, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import SettingsSection from '../SettingsSection';
import { Button } from '@/components/primitives/button';
import { Badge } from '@/components/primitives/badge';
import { Progress } from '@/components/primitives/progress';
import {
  IconActivity,
  IconCheck,
  IconDownload,
  IconEye,
  IconLoader,
  IconLock,
  IconRotateCcw,
  IconShieldAlert,
  IconShieldCheck,
  IconUser,
  IconWrench,
} from '@/components/features/icons/PremiumIcons';
import {
  dualTrackAuditService,
  type DualTrackAuditEntryItem,
  type DualTrackAuditStatsResponse,
} from '@/services/dualTrackAudit';
import { toast } from '@/hooks/shared/useToast';

export const DualTrackAuditDashboard = memo(() => {
  const t = useTranslations('settings.dualTrackAudit');
  const [stats, setStats] = useState<DualTrackAuditStatsResponse | null>(null);
  const [entries, setEntries] = useState<DualTrackAuditEntryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      const [statsData, entriesData] = await Promise.all([
        dualTrackAuditService.getStats(),
        dualTrackAuditService.getEntries({ limit: 50 }),
      ]);
      setStats(statsData);
      setEntries(entriesData);
    } catch {
      // Graceful fallback
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleExport = useCallback(
    (format: 'json' | 'csv' | 'markdown') => {
      const url = dualTrackAuditService.getExportUrl({ format });
      window.open(url, '_blank');
      toast({
        title: t('exportTriggeredTitle'),
        description: t('exportTriggeredDesc', { format: format.toUpperCase() }),
      });
    },
    [t]
  );

  return (
    <SettingsSection
      title={t('title')}
      description={t('description')}
    >
      <div className="space-y-6">
        {/* KPI Row */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <div className="rounded-xl border border-border/40 bg-background/50 p-3.5 space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-medium">
              <IconActivity className="w-3.5 h-3.5 text-primary" />
              {t('totalIntents')}
            </div>
            <div className="text-2xl font-bold tracking-tight">
              {stats ? stats.totalEntries : '...'}
            </div>
            <div className="text-[11px] text-muted-foreground">
              {t('failClosedLogged')}
            </div>
          </div>

          <div className="rounded-xl border border-border/40 bg-background/50 p-3.5 space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-medium">
              <IconShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              {t('compliancePassRate')}
            </div>
            <div className="text-2xl font-bold text-emerald-500 tracking-tight">
              {stats ? `${(stats.complianceRate * 100).toFixed(1)}%` : '...'}
            </div>
            <div className="text-[11px] text-muted-foreground">
              {stats ? t('permittedVsTotal', { count: stats.permittedCount }) : ''}
            </div>
          </div>

          <div className="rounded-xl border border-border/40 bg-background/50 p-3.5 space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-medium">
              <IconShieldAlert className="w-3.5 h-3.5 text-amber-500" />
              {t('policyRefusals')}
            </div>
            <div className="text-2xl font-bold text-amber-500 tracking-tight">
              {stats ? stats.refusedCount : '...'}
            </div>
            <div className="text-[11px] text-muted-foreground">
              {stats ? t('failedExecution', { count: stats.failedCount }) : ''}
            </div>
          </div>

          <div className="rounded-xl border border-border/40 bg-background/50 p-3.5 space-y-1.5">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground font-medium">
              <IconUser className="w-3.5 h-3.5 text-sky-500" />
              {t('takeTheWheelCount')}
            </div>
            <div className="text-2xl font-bold text-sky-500 tracking-tight">
              {stats ? stats.humanTakeTheWheelCount : '...'}
            </div>
            <div className="text-[11px] text-muted-foreground">
              {t('humanInterceptionTagged')}
            </div>
          </div>
        </div>

        {/* Top Rules Telemetry */}
        {stats && stats.topRulesTriggered.length > 0 && (
          <div className="space-y-3">
            <h4 className="text-sm font-semibold">{t('topRulesTitle')}</h4>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {stats.topRulesTriggered.slice(0, 4).map((rule) => (
                <div
                  key={rule.ruleName}
                  className="rounded-lg border border-border/30 bg-muted/20 p-3 space-y-2 text-xs"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-medium truncate max-w-[200px]">{rule.ruleName}</span>
                    <Badge variant={rule.refusalRate > 0.3 ? 'destructive' : 'secondary'} className="text-[10px] h-5">
                      {t('refusalRate', { rate: (rule.refusalRate * 100).toFixed(0) })}
                    </Badge>
                  </div>
                  <Progress value={Math.min(100, Math.max(5, rule.refusalRate * 100))} className="h-1.5" />
                  <div className="flex justify-between text-[11px] text-muted-foreground">
                    <span>{t('hitsSummary', { total: rule.triggerCount, refused: rule.refusedCount })}</span>
                    <span>{t('permittedSummary', { permitted: rule.permittedCount })}</span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Action Table & Export Bar */}
        <div className="space-y-3 pt-2 border-t border-border/30">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h4 className="text-sm font-semibold">{t('recentAuditTrail')}</h4>
            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleExport('json')}
                className="h-7 text-xs gap-1 px-2"
              >
                <IconDownload className="w-3 h-3" />
                JSON
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleExport('csv')}
                className="h-7 text-xs gap-1 px-2"
              >
                <IconDownload className="w-3 h-3" />
                CSV
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleExport('markdown')}
                className="h-7 text-xs gap-1 px-2"
              >
                <IconDownload className="w-3 h-3" />
                Markdown
              </Button>
            </div>
          </div>

          {entries.length === 0 ? (
            <div className="text-xs text-muted-foreground py-6 text-center border border-dashed rounded-lg border-border/40">
              {loading ? t('loadingEntries') : t('noEntriesYet')}
            </div>
          ) : (
            <div className="rounded-lg border border-border/30 divide-y divide-border/20 max-h-64 overflow-y-auto">
              {entries.map((entry) => (
                <div key={entry.entryId} className="p-2.5 space-y-1.5 text-xs">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Badge
                        variant={
                          entry.outcome === 'PERMITTED'
                            ? 'default'
                            : entry.outcome === 'REFUSED'
                            ? 'destructive'
                            : 'outline'
                        }
                        className="text-[10px] h-4 px-1.5"
                      >
                        {entry.outcome}
                      </Badge>
                      <span className="font-mono text-foreground font-medium">{entry.toolName}</span>
                      {entry.isHumanTakeTheWheel && (
                        <Badge variant="outline" className="text-[10px] h-4 border-sky-500/50 text-sky-500 px-1">
                          TakeTheWheel
                        </Badge>
                      )}
                    </div>
                    <div className="text-[11px] text-muted-foreground flex items-center gap-2">
                      {entry.latencyMs > 0 && <span>{entry.latencyMs}ms</span>}
                      <span>{new Date(entry.createdAt).toLocaleTimeString()}</span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setExpandedId(expandedId === entry.entryId ? null : entry.entryId)}
                        className="h-5 w-5 p-0"
                      >
                        <IconEye className="w-3 h-3 text-muted-foreground hover:text-foreground" />
                      </Button>
                    </div>
                  </div>

                  <div className="text-muted-foreground text-[11px] truncate">
                    {entry.intentSummary}
                  </div>

                  {expandedId === entry.entryId && (
                    <div className="mt-2 rounded bg-muted/40 p-2 text-[11px] font-mono space-y-1">
                      <div>
                        <span className="text-muted-foreground">Rule: </span>
                        <span className="text-foreground">{entry.ruleName}</span>
                      </div>
                      <div>
                        <span className="text-muted-foreground">Session ID: </span>
                        <span className="text-foreground">{entry.sessionId}</span>
                      </div>
                      {entry.errorMessage && (
                        <div className="text-destructive">
                          <span className="text-muted-foreground">Error/Reason: </span>
                          {entry.errorMessage}
                        </div>
                      )}
                      <div>
                        <span className="text-muted-foreground">Sanitized Args: </span>
                        <pre className="mt-1 text-[10px] max-h-24 overflow-y-auto whitespace-pre-wrap">
                          {JSON.stringify(entry.rawIntentArgs, null, 2)}
                        </pre>
                      </div>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </SettingsSection>
  );
});

DualTrackAuditDashboard.displayName = 'DualTrackAuditDashboard';
