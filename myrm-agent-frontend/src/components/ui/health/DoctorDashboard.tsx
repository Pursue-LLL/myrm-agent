'use client';
/**
 * [INPUT]
 * - src/services/runtime-health.ts::getRuntimeDoctor (POS: 运行时健康API客户端)
 * - src/components/ui/health/HealthTrendChart.tsx::HealthTrendChart (POS: 健康趋势图表组件)
 * - src/components/ui/health/GuidedRepairCard.tsx::GuidedRepairCard (POS: 引导式修复卡片组件)
 *
 * [OUTPUT]
 * - DoctorDashboard: 系统诊断核心视图组件。
 *
 * [POS]
 * 系统诊断看板主组件。汇聚了各项健康指标和状态报告，并提供操作指引。
 */

import { useEffect, useState, useCallback } from 'react';
import { useTranslations } from 'next-intl';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { cn } from '@/lib/utils/classnameUtils';
import { getRuntimeDoctor, type DoctorResponse, type HealthReport, type HealthStatus } from '@/services/runtime-health';
import { HealthTrendChart } from './HealthTrendChart';
import { GuidedRepairCard } from './GuidedRepairCard';

// Custom Premium Icons
const ActivityIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
  </svg>
);
const AlertCircleIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="12" cy="12" r="10" />
    <line x1="12" y1="8" x2="12" y2="12" />
    <line x1="12" y1="16" x2="12.01" y2="16" />
  </svg>
);
const CheckCircleIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14" />
    <polyline points="22 4 12 14.01 9 11.01" />
  </svg>
);
const XCircleIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="12" cy="12" r="10" />
    <line x1="15" y1="9" x2="9" y2="15" />
    <line x1="9" y1="9" x2="15" y2="15" />
  </svg>
);
const RefreshIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
    <polyline points="3 3 3 8 8 8" />
  </svg>
);
const SearchIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="1.5"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <circle cx="11" cy="11" r="8" />
    <line x1="21" y1="21" x2="16.65" y2="16.65" />
  </svg>
);

// Custom SVG Icons
const PackageIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
    <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
    <line x1="12" y1="22.08" x2="12" y2="12" />
  </svg>
);

const ServerIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <rect x="2" y="2" width="20" height="8" rx="2" ry="2" />
    <rect x="2" y="14" width="20" height="8" rx="2" ry="2" />
    <line x1="6" y1="6" x2="6.01" y2="6" />
    <line x1="6" y1="18" x2="6.01" y2="18" />
  </svg>
);

const IdeaIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M15 14c.2-1 .7-1.7 1.5-2.5 1-.9 1.5-2.2 1.5-3.5A6 6 0 0 0 6 8c0 1 .2 2.2 1.5 3.5.7.9 1.2 1.5 1.5 2.5" />
    <path d="M9 18h6" />
    <path d="M10 22h4" />
  </svg>
);

const WrenchIcon = ({ className = 'w-4 h-4' }) => (
  <svg
    xmlns="http://www.w3.org/2000/svg"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth="2"
    strokeLinecap="round"
    strokeLinejoin="round"
    className={className}
  >
    <path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z" />
  </svg>
);

export function DoctorDashboard() {
  const t = useTranslations('settings.systemHealth.doctor');
  const [data, setData] = useState<DoctorResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<'all' | HealthStatus>('all');

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

  useEffect(() => {
    fetchHealth();
    let timeoutId: NodeJS.Timeout;
    const handleSseEvent = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => fetchHealth(), 1000);
    };
    window.addEventListener('health_status_updated', handleSseEvent);
    window.addEventListener('app_resync_required', handleSseEvent);
    return () => {
      window.removeEventListener('health_status_updated', handleSseEvent);
      window.removeEventListener('app_resync_required', handleSseEvent);
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
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  };

  return (
    <Card className="bg-zinc-900 border-zinc-800 text-zinc-100">
      <CardHeader className="flex flex-row items-start justify-between pb-2">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2">
            <ActivityIcon className="h-5 w-5 text-indigo-400" />
            {t('title')}
          </CardTitle>
          <CardDescription className="text-zinc-400">{t('description')}</CardDescription>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchHealth}
          disabled={loading}
          className="bg-zinc-800 border-zinc-700 hover:bg-zinc-700 text-xs"
        >
          <RefreshIcon className={cn('h-3 w-3 mr-2', loading && 'animate-spin')} />
          {t('retry')}
        </Button>
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

            <HealthTrendChart />

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
