'use client';
/**
 * [INPUT]
 * - src/services/runtime-health.ts::getRuntimeDoctor (POS: 运行时健康API客户端)
 * - components/features/health/GuidedRepairCard.tsx::GuidedRepairCard (POS: 引导式修复卡片组件)
 * - components/features/health/DoctorReportRow.tsx::DoctorReportRow, STATUS_TEXT_CLASS (POS: 单条体检结果行)
 * - components/features/health/doctorReportView.ts::describeReport (POS: 体检行本地化文案描述)
 * - components/features/health/doctor-icons.tsx::* (POS: 诊断面板SVG图标)
 * - lib/utils/diagnostic-export.ts::copyDiagnosticMarkdown, downloadDiagnosticJson (POS: 诊断导出工具)
 *
 * [OUTPUT]
 * - DoctorDashboard: 系统诊断核心视图组件。
 *
 * [POS]
 * 系统诊断看板主组件。汇聚了各项健康指标和状态报告，并提供操作指引与诊断导出；
 * 英文原文只出现在可展开的技术详情里，搜索同时匹配本地化文案与英文原文。
 */

import { useEffect, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { IconChevronDown, IconChevronUp } from '@/components/features/icons/PremiumIcons';
import { cn } from '@/lib/utils/classnameUtils';
import { getRuntimeDoctor, type DoctorResponse, type HealthReport, type HealthStatus } from '@/services/runtime-health';
import { copyDiagnosticMarkdown, downloadDiagnosticJson } from '@/lib/utils/diagnostic-export';
import { GuidedRepairCard } from './GuidedRepairCard';
import { DoctorReportRow, STATUS_TEXT_CLASS } from './DoctorReportRow';
import { describeReport, type DoctorText } from './doctorReportView';
import {
  ActivityIcon,
  XCircleIcon,
  RefreshIcon,
  SearchIcon,
  PackageIcon,
  ServerIcon,
  WrenchIcon,
  ClipboardCopyIcon,
  DownloadIcon,
  CheckIcon,
} from './doctor-icons';

interface DoctorRowModel {
  report: HealthReport;
  title: string;
  summary: string;
  technical: { label: string; value: string }[];
}

const HEALTH_TIER_BG = { pass: 'bg-emerald-500/10', warn: 'bg-amber-500/10', fail: 'bg-red-500/10' } as const;

export function DoctorDashboard() {
  const t = useTranslations('settings.systemHealth.doctor');
  const [data, setData] = useState<DoctorResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | HealthStatus>('all');
  const [copySuccess, setCopySuccess] = useState(false);
  const [technicalOpen, setTechnicalOpen] = useState(false);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const json = await getRuntimeDoctor();
      setData({ ...json, repair_actions: json.repair_actions ?? [] });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('unknownError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  const handleCopyMarkdown = useCallback(async () => {
    if (!data) {
      return;
    }
    const ok = await copyDiagnosticMarkdown(data);
    if (ok) {
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } else {
      toast.error(t('exportCopyFailed'));
    }
  }, [data, t]);

  const handleDownloadJson = useCallback(() => {
    if (!data) {
      return;
    }
    downloadDiagnosticJson(data);
  }, [data]);

  useEffect(() => {
    fetchHealth();
    let timeoutId: NodeJS.Timeout;
    const handleResync = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => fetchHealth(), 1000);
    };
    window.addEventListener('app_resync_required', handleResync);
    return () => {
      window.removeEventListener('app_resync_required', handleResync);
      clearTimeout(timeoutId);
    };
  }, [fetchHealth]);

  if (loading && !data && !error) {
    return (
      <div className="flex items-center gap-2 p-4 text-muted-foreground">
        <ActivityIcon className="animate-spin" /> {t('loading')}
      </div>
    );
  }

  const resolveText = (text: DoctorText): string =>
    'key' in text ? t(text.key, text.values as Parameters<typeof t>[1]) : text.text;

  const toRowModel = (report: HealthReport): DoctorRowModel => {
    const view = describeReport(report, (key) => t.has(key));
    return {
      report,
      title: resolveText(view.title),
      summary: resolveText(view.summary),
      technical: view.technical.map(({ labelKey, value }) => ({ label: t(labelKey), value })),
    };
  };

  // The search covers what the user reads and the English original a bug report or a teammate would quote.
  const filterRows = (reports: HealthReport[]): DoctorRowModel[] =>
    reports.map(toRowModel).filter(({ report, title, summary }) => {
      const query = searchQuery.toLowerCase();
      const matchesSearch =
        searchQuery === '' ||
        [title, summary, report.component_name, report.message].some((text) => text.toLowerCase().includes(query));
      const matchesStatus = statusFilter === 'all' || report.status === statusFilter;
      return matchesSearch && matchesStatus;
    });

  const harnessRows = filterRows(data?.harness || []);
  const serverRows = filterRows(data?.server || []);
  const allRows = [...harnessRows, ...serverRows];

  const totalComponents = allRows.length;
  const passCount = allRows.filter(({ report }) => report.status === 'pass').length;
  const warnCount = allRows.filter(({ report }) => report.status === 'warn').length;
  const failCount = allRows.filter(({ report }) => report.status === 'fail').length;
  const healthScore = totalComponents > 0 ? Math.round((passCount / totalComponents) * 100) : 100;

  const getHealthTier = (score: number): { label: string; status: HealthStatus } => {
    if (score >= 90) {
      return { label: t('statusHealthy'), status: 'pass' };
    }
    if (score >= 50) {
      return { label: t('statusDegraded'), status: 'warn' };
    }
    return { label: t('statusCritical'), status: 'fail' };
  };

  const healthTier = getHealthTier(healthScore);

  const renderReportGroup = (rows: DoctorRowModel[], title: string, icon: React.ReactNode) => {
    if (rows.length === 0) {
      return null;
    }

    const groupPassCount = rows.filter(({ report }) => report.status === 'pass').length;

    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground/80">
            <span>{icon}</span>
            <span>{title}</span>
            <span className="text-xs text-muted-foreground">
              ({groupPassCount}/{rows.length} {t('healthy')})
            </span>
          </h3>
        </div>
        <div className="grid gap-3">
          {rows.map(({ report, title: rowTitle, summary, technical }, idx) => (
            <DoctorReportRow
              key={idx}
              report={report}
              title={rowTitle}
              summary={summary}
              statusLabel={t(`status.${report.status}`)}
              openSettingsLabel={t('desktopOpenSettings')}
              technicalOpen={technicalOpen}
              technical={technical}
            />
          ))}
        </div>
      </div>
    );
  };

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              <ActivityIcon className="h-5 w-5 text-primary" />
              {t('title')}
            </CardTitle>
            <CardDescription>{t('description')}</CardDescription>
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <Button
              variant="outline"
              size="sm"
              onClick={handleCopyMarkdown}
              disabled={!data}
              className="text-xs"
              title={t('exportCopyMarkdown')}
            >
              {copySuccess ? (
                <CheckIcon className={cn('mr-1.5 h-3 w-3', STATUS_TEXT_CLASS.pass)} />
              ) : (
                <ClipboardCopyIcon className="mr-1.5 h-3 w-3" />
              )}
              {copySuccess ? t('exportCopied') : t('exportCopyMarkdown')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownloadJson}
              disabled={!data}
              className="text-xs"
              title={t('exportDownloadJson')}
            >
              <DownloadIcon className="mr-1.5 h-3 w-3" />
              {t('exportDownloadJson')}
            </Button>
            <Button variant="outline" size="sm" onClick={fetchHealth} disabled={loading} className="text-xs">
              <RefreshIcon className={cn('mr-1.5 h-3 w-3', loading && 'animate-spin')} />
              {t('retry')}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {error ? (
          <div className={cn('flex items-center gap-2 p-4', STATUS_TEXT_CLASS.fail)}>
            <XCircleIcon /> {t('unreachable', { error })}
          </div>
        ) : (
          <div className="space-y-6">
            <div className="flex flex-col gap-3 sm:flex-row">
              <div className="relative flex-1">
                <SearchIcon className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 transform text-muted-foreground" />
                <Input
                  placeholder={t('searchPlaceholder')}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9"
                />
              </div>
              <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as 'all' | HealthStatus)}>
                <SelectTrigger className="w-full sm:w-[180px]">
                  <SelectValue placeholder={t('filterPlaceholder')} />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">{t('filterAll')}</SelectItem>
                  <SelectItem value="pass">{t('filterPass')}</SelectItem>
                  <SelectItem value="fail">{t('filterFail')}</SelectItem>
                  <SelectItem value="warn">{t('filterWarn')}</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className={cn('rounded-lg border border-border p-4', HEALTH_TIER_BG[healthTier.status])}>
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h3 className="text-lg font-semibold">{t('healthScore', { score: healthScore })}</h3>
                  <p className="text-sm text-muted-foreground">
                    {t('healthSummary', { pass: passCount, fail: failCount, warn: warnCount })}
                  </p>
                </div>
                <Badge
                  className={cn(
                    'shrink-0 text-sm',
                    HEALTH_TIER_BG[healthTier.status],
                    STATUS_TEXT_CLASS[healthTier.status],
                  )}
                >
                  {healthTier.label}
                </Badge>
              </div>
            </div>

            {data?.repair_actions && data.repair_actions.length > 0 && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="flex items-center gap-2 text-sm font-semibold text-foreground/80">
                    <WrenchIcon className="h-4 w-4 text-muted-foreground" />
                    <span>{t('repairTitle')}</span>
                    <span className="text-xs text-muted-foreground">({data.repair_actions.length})</span>
                  </h3>
                </div>
                <div className="grid gap-3">
                  {data.repair_actions.map((action) => (
                    <GuidedRepairCard key={action.action_id} action={action} onExecuted={fetchHealth} />
                  ))}
                </div>
              </div>
            )}

            {allRows.length > 0 && (
              <div className="flex justify-end">
                <button
                  type="button"
                  aria-expanded={technicalOpen}
                  onClick={() => setTechnicalOpen((open) => !open)}
                  className="inline-flex items-center gap-1 rounded text-xs font-medium text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                >
                  {t('technical.toggle')}
                  {technicalOpen ? (
                    <IconChevronUp className="h-3.5 w-3.5" />
                  ) : (
                    <IconChevronDown className="h-3.5 w-3.5" />
                  )}
                </button>
              </div>
            )}

            {renderReportGroup(harnessRows, t('layerHarness'), <PackageIcon className="h-4 w-4" />)}
            {renderReportGroup(serverRows, t('layerServer'), <ServerIcon className="h-4 w-4" />)}

            {allRows.length === 0 && <div className="p-4 text-center text-muted-foreground">{t('noProbes')}</div>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
