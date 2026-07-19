'use client';
/**
 * [INPUT]
 * - src/services/runtime-health.ts::getRuntimeDoctor (POS: 运行时健康API客户端)
 * - components/features/health/GuidedRepairCard.tsx::GuidedRepairCard (POS: 引导式修复卡片组件)
 * - components/features/health/doctor-icons.tsx::* (POS: 诊断面板SVG图标)
 * - lib/utils/diagnostic-export.ts::copyDiagnosticMarkdown, downloadDiagnosticJson (POS: 诊断导出工具)
 *
 * [OUTPUT]
 * - DoctorDashboard: 系统诊断核心视图组件。
 *
 * [POS]
 * 系统诊断看板主组件。汇聚了各项健康指标和状态报告，并提供操作指引与诊断导出。
 */

import { useEffect, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { toast } from 'sonner';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Badge } from '@/components/primitives/badge';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { cn } from '@/lib/utils/classnameUtils';
import { getRuntimeDoctor, type DoctorResponse, type HealthReport, type HealthStatus } from '@/services/runtime-health';
import { copyDiagnosticMarkdown, downloadDiagnosticJson } from '@/lib/utils/diagnostic-export';
import { GuidedRepairCard } from './GuidedRepairCard';
import {
  ActivityIcon, AlertCircleIcon, CheckCircleIcon, XCircleIcon, RefreshIcon,
  SearchIcon, PackageIcon, ServerIcon, IdeaIcon, WrenchIcon,
  ClipboardCopyIcon, DownloadIcon, CheckIcon,
} from './doctor-icons';
import {
  openPermissionDeepLinkWithGuideFallback,
  pickSettingsDeepLinkFromMeta,
} from '@/lib/desktop/permissionDeepLink';

export function DoctorDashboard() {
  const t = useTranslations('settings.systemHealth.doctor');
  const [data, setData] = useState<DoctorResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | HealthStatus>('all');
  const [copySuccess, setCopySuccess] = useState(false);

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
    if (!data) return;
    const ok = await copyDiagnosticMarkdown(data);
    if (ok) {
      setCopySuccess(true);
      setTimeout(() => setCopySuccess(false), 2000);
    } else {
      toast.error(t('exportCopyFailed'));
    }
  }, [data, t]);

  const handleDownloadJson = useCallback(() => {
    if (!data) return;
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
      <div className="p-4 text-zinc-400 flex items-center gap-2">
        <ActivityIcon className="animate-spin" /> {t('loading')}
      </div>
    );
  }

  const filterReports = (reports: DoctorResponse['harness']) => {
    return reports.filter((report) => {
      const matchesSearch =
        searchQuery === '' ||
        report.component_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        report.message.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesStatus = statusFilter === 'all' || report.status === statusFilter;
      return matchesSearch && matchesStatus;
    });
  };

  const harnessReports = filterReports(data?.harness || []);
  const serverReports = filterReports(data?.server || []);
  const allReports = [...harnessReports, ...serverReports];

  const totalComponents = allReports.length;
  const passCount = allReports.filter((r) => r.status === 'pass').length;
  const warnCount = allReports.filter((r) => r.status === 'warn').length;
  const failCount = allReports.filter((r) => r.status === 'fail').length;
  const healthScore = totalComponents > 0 ? Math.round((passCount / totalComponents) * 100) : 100;

  const getHealthStatus = (score: number) => {
    if (score >= 90) return { label: t('statusHealthy'), color: 'text-green-500', bg: 'bg-green-500/10' };
    if (score >= 50) return { label: t('statusDegraded'), color: 'text-yellow-500', bg: 'bg-yellow-500/10' };
    return { label: t('statusCritical'), color: 'text-red-500', bg: 'bg-red-500/10' };
  };

  const healthStatus = getHealthStatus(healthScore);

  const renderReportGroup = (reports: HealthReport[], title: string, icon: React.ReactNode) => {
    if (reports.length === 0) return null;

    const groupPassCount = reports.filter((r) => r.status === 'pass').length;
    const groupTotal = reports.length;

    return (
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-2">
            <span>{icon}</span>
            <span>{title}</span>
            <span className="text-xs text-zinc-500">
              ({groupPassCount}/{groupTotal} {t('healthy')})
            </span>
          </h3>
        </div>
        <div className="grid gap-3">
          {reports.map((report, idx) => (
            <div
              key={idx}
              className="flex flex-col md:flex-row items-start md:items-center justify-between p-3 rounded-lg bg-zinc-800/30 border border-zinc-800/50"
            >
              <div className="flex items-center gap-3">
                {report.status === 'pass' && <CheckCircleIcon className="h-4 w-4 text-green-500" />}
                {report.status === 'warn' && <AlertCircleIcon className="h-4 w-4 text-yellow-500" />}
                {report.status === 'fail' && <XCircleIcon className="h-4 w-4 text-red-500" />}
                <div>
                  <h4 className="font-medium text-sm">{report.component_name}</h4>
                  <p className="text-xs text-zinc-400">
                    {report.code
                      ? t(`errors.${report.code}.message`, report.meta_data as any) || report.message
                      : report.message}
                  </p>
                  {report.detail && <p className="text-xs text-zinc-500 mt-0.5 font-mono">{report.detail}</p>}
                </div>
              </div>
              <div className="mt-2 md:mt-0 flex flex-col items-end gap-1">
                <Badge
                  variant={
                    report.status === 'pass' ? 'default' : report.status === 'warn' ? 'secondary' : 'destructive'
                  }
                  className={cn(
                    'text-xs',
                    report.status === 'pass'
                      ? 'bg-green-500/10 text-green-500 hover:bg-green-500/20'
                      : report.status === 'warn'
                        ? 'bg-yellow-500/10 text-yellow-500 hover:bg-yellow-500/20'
                        : 'bg-red-500/10 text-red-500 hover:bg-red-500/20',
                  )}
                >
                  {report.status.toUpperCase()}
                </Badge>
                {report.fix_suggestion && (
                  <div className="flex items-center gap-1 mt-0.5 text-xs text-indigo-400 max-w-[200px] text-right">
                    <IdeaIcon className="w-3 h-3 flex-shrink-0" />
                    <span>{report.fix_suggestion}</span>
                  </div>
                )}
                {report.component_name === 'DesktopControl' &&
                  report.status === 'warn' &&
                  pickSettingsDeepLinkFromMeta(report.meta_data ?? undefined) && (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="mt-1 h-7 text-xs bg-zinc-800 border-zinc-700 hover:bg-zinc-700"
                      onClick={() => {
                        const link = pickSettingsDeepLinkFromMeta(report.meta_data ?? undefined);
                        if (link) {
                          const platform =
                            report.meta_data &&
                            typeof report.meta_data.platform === 'string'
                              ? report.meta_data.platform
                              : null;
                          openPermissionDeepLinkWithGuideFallback(link, platform);
                        }
                      }}
                    >
                      {t('desktopOpenSettings')}
                    </Button>
                  )}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <Card className="bg-zinc-900 border-zinc-800 text-zinc-100">
      <CardHeader className="pb-2">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2">
              <ActivityIcon className="h-5 w-5 text-indigo-400" />
              {t('title')}
            </CardTitle>
            <CardDescription className="text-zinc-400">{t('description')}</CardDescription>
          </div>
          <div className="flex items-center gap-1.5 flex-wrap">
            <Button
              variant="outline"
              size="sm"
              onClick={handleCopyMarkdown}
              disabled={!data}
              className="bg-zinc-800 border-zinc-700 hover:bg-zinc-700 text-xs"
              title={t('exportCopyMarkdown')}
            >
              {copySuccess ? (
                <CheckIcon className="h-3 w-3 mr-1.5 text-green-400" />
              ) : (
                <ClipboardCopyIcon className="h-3 w-3 mr-1.5" />
              )}
              {copySuccess ? t('exportCopied') : t('exportCopyMarkdown')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleDownloadJson}
              disabled={!data}
              className="bg-zinc-800 border-zinc-700 hover:bg-zinc-700 text-xs"
              title={t('exportDownloadJson')}
            >
              <DownloadIcon className="h-3 w-3 mr-1.5" />
              {t('exportDownloadJson')}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={fetchHealth}
              disabled={loading}
              className="bg-zinc-800 border-zinc-700 hover:bg-zinc-700 text-xs"
            >
              <RefreshIcon className={cn('h-3 w-3 mr-1.5', loading && 'animate-spin')} />
              {t('retry')}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {error ? (
          <div className="p-4 text-red-400 flex items-center gap-2">
            <XCircleIcon /> {t('unreachable', { error })}
          </div>
        ) : (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row gap-3">
              <div className="relative flex-1">
                <SearchIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-zinc-500" />
                <Input
                  placeholder={t('searchPlaceholder')}
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-9 bg-zinc-800 border-zinc-700 text-zinc-100 placeholder:text-zinc-500"
                />
              </div>
              <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value as 'all' | HealthStatus)}>
                <SelectTrigger className="w-full sm:w-[180px] bg-zinc-800 border-zinc-700">
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

            <div className={cn('p-4 rounded-lg border', healthStatus.bg, 'border-zinc-800')}>
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-lg font-semibold">{t('healthScore', { score: healthScore })}</h3>
                  <p className="text-sm text-zinc-400">
                    {t('healthSummary', { pass: passCount, fail: failCount, warn: warnCount })}
                  </p>
                </div>
                <Badge className={cn('text-sm', healthStatus.bg, healthStatus.color)}>{healthStatus.label}</Badge>
              </div>
            </div>

            {data?.repair_actions && data.repair_actions.length > 0 && (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-zinc-300 flex items-center gap-2">
                    <WrenchIcon className="w-4 h-4 text-zinc-400" />
                    <span>{t('repairTitle')}</span>
                    <span className="text-xs text-zinc-500">({data.repair_actions.length})</span>
                  </h3>
                </div>
                <div className="grid gap-3">
                  {data.repair_actions.map((action) => (
                    <GuidedRepairCard key={action.action_id} action={action} onExecuted={fetchHealth} />
                  ))}
                </div>
              </div>
            )}

            {renderReportGroup(harnessReports, t('layerHarness'), <PackageIcon className="w-4 h-4" />)}
            {renderReportGroup(serverReports, t('layerServer'), <ServerIcon className="w-4 h-4" />)}

            {allReports.length === 0 && <div className="p-4 text-center text-zinc-500">{t('noProbes')}</div>}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
