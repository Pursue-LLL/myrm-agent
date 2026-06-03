'use client';
/**
 * [INPUT]
 * - src/lib/api.ts::apiRequest (POS: API 请求客户端)
 * - src/services/runtime-health.ts::HealthReport (POS: 健康报告类型定义)
 *
 * [OUTPUT]
 * - HealthTrendChart: 24小时系统健康分数走势图。
 *
 * [POS]
 * 健康趋势图组件。以折线图形式直观展示系统的健康发展趋势并支持钻取。
 */

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from '@/components/primitives/dialog';
import { Badge } from '@/components/primitives/badge';
import { cn } from '@/lib/utils/classnameUtils';
import { apiRequest } from '@/lib/api';
import type { HealthReport } from '@/services/runtime-health';

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

interface HealthDataPoint {
  timestamp: string;
  status: 'pass' | 'warn' | 'fail';
  score: number;
  components?: string;
}

interface ProcessedDataPoint extends HealthDataPoint {
  timeLabel: string;
  fullTime: string;
  harness?: HealthReport[];
  server?: HealthReport[];
}

type TimeRange = '24' | '168';

export function HealthTrendChart() {
  const t = useTranslations('settings.systemHealth');

  const [data, setData] = useState<ProcessedDataPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [timeRange, setTimeRange] = useState<TimeRange>('24');

  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedPoint, setSelectedPoint] = useState<ProcessedDataPoint | null>(null);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const rawData = await apiRequest<HealthDataPoint[]>(`/health/history?hours=${timeRange}`, { silent: true });
        const dataArray = Array.isArray(rawData) ? rawData : [];

        const processed = dataArray.map((pt: HealthDataPoint) => {
          const date = new Date(pt.timestamp);

          let parsedHarness: HealthReport[] = [];
          let parsedServer: HealthReport[] = [];
          if (pt.components) {
            try {
              const compObj = JSON.parse(pt.components);
              parsedHarness = compObj.harness || [];
              parsedServer = compObj.server || [];
            } catch (e) {
              console.error('Failed to parse component details', e);
            }
          }

          return {
            ...pt,
            timeLabel:
              timeRange === '24'
                ? date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
                : date.toLocaleDateString([], { month: 'short', day: 'numeric', hour: '2-digit' }),
            fullTime: date.toLocaleString(),
            harness: parsedHarness,
            server: parsedServer,
          };
        });

        setData(processed);
        setError(null);
      } catch (err) {
        setError(err instanceof Error ? err.message : t('trend.unknownError'));
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    let timeoutId: NodeJS.Timeout;
    const handleSseEvent = () => {
      clearTimeout(timeoutId);
      timeoutId = setTimeout(() => fetchData(), 1000);
    };
    window.addEventListener('health_status_updated', handleSseEvent);
    window.addEventListener('app_resync_required', handleSseEvent);
    return () => {
      window.removeEventListener('health_status_updated', handleSseEvent);
      window.removeEventListener('app_resync_required', handleSseEvent);
      clearTimeout(timeoutId);
    };
  }, [timeRange, t]);

  const handlePointClick = (dataPoint: ProcessedDataPoint) => {
    setSelectedPoint(dataPoint);
    setDialogOpen(true);
  };

  const renderReportItem = (report: HealthReport, index: number) => {
    const statusConfig = {
      pass: {
        icon: CheckCircleIcon,
        color: 'text-emerald-500',
        bg: 'bg-emerald-500/10',
        border: 'border-emerald-500/20',
      },
      fail: { icon: XCircleIcon, color: 'text-rose-500', bg: 'bg-rose-500/10', border: 'border-rose-500/20' },
      warn: { icon: AlertCircleIcon, color: 'text-amber-500', bg: 'bg-amber-500/10', border: 'border-amber-500/20' },
    }[report.status];

    const Icon = statusConfig.icon;

    return (
      <div
        key={`${report.component_name}-${index}`}
        className={cn('p-3 rounded-lg border', statusConfig.border, statusConfig.bg)}
      >
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <Icon className={cn('w-4 h-4', statusConfig.color)} />
            <span className="font-medium text-sm">{report.component_name}</span>
          </div>
          <Badge variant="outline" className={cn('text-[10px] uppercase', statusConfig.color, statusConfig.border)}>
            {report.status}
          </Badge>
        </div>
        <p className="text-xs text-zinc-600 dark:text-zinc-400 mt-1.5">
          {report.code ? t(`errors.${report.code}.message`, report.meta_data as any) || report.message : report.message}
        </p>
        {report.detail && <p className="text-xs text-zinc-500 dark:text-zinc-500 mt-1 font-mono">{report.detail}</p>}
        {report.fix_suggestion && (
          <p className="text-xs text-amber-600 dark:text-amber-400 mt-1.5 font-medium flex items-center gap-1">
            <IdeaIcon className="shrink-0" />
            <span>{report.fix_suggestion}</span>
          </p>
        )}
      </div>
    );
  };

  const CustomDot = (props: { cx?: number; cy?: number; payload?: ProcessedDataPoint }) => {
    const { cx, cy, payload } = props;
    if (cx == null || cy == null) return null;

    let fill = '#8b5cf6'; // default
    if (payload.status === 'fail') fill = '#ef4444';
    else if (payload.status === 'warn') fill = '#f59e0b';
    else if (payload.status === 'pass') fill = '#10b981';

    return (
      <circle
        cx={cx}
        cy={cy}
        r={4}
        fill={fill}
        stroke="var(--background)"
        strokeWidth={2}
        className="cursor-pointer hover:r-6 transition-all duration-200"
        onClick={() => handlePointClick(payload)}
      />
    );
  };

  if (error) {
    return (
      <Card className="border-rose-500/20 bg-rose-500/5 mt-6">
        <CardContent className="p-4 text-sm text-rose-500 flex items-center gap-2">
          <AlertCircleIcon className="w-4 h-4" />
          {t('trend.errorPrefix')}: {error}
        </CardContent>
      </Card>
    );
  }

  return (
    <>
      <Card className="mt-6 border-zinc-200 dark:border-zinc-800 overflow-hidden">
        <CardHeader className="pb-2 border-b border-zinc-100 dark:border-zinc-800/50 bg-zinc-50/50 dark:bg-zinc-900/20">
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base">{t('trend.title')}</CardTitle>
              <CardDescription className="text-xs mt-1">{t('trend.description')}</CardDescription>
            </div>
            <Select value={timeRange} onValueChange={(v) => setTimeRange(v as TimeRange)}>
              <SelectTrigger className="w-[130px] h-8 text-xs bg-background">
                <SelectValue placeholder={t('trend.timeRange.label')} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="24" className="text-xs">
                  {t('trend.timeRange.last24h')}
                </SelectItem>
                <SelectItem value="168" className="text-xs">
                  {t('trend.timeRange.last7d')}
                </SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent className="p-6">
          {loading && data.length === 0 ? (
            <div className="h-[250px] w-full flex items-center justify-center text-sm text-zinc-500 animate-pulse">
              {t('trend.loading')}
            </div>
          ) : data.length === 0 ? (
            <div className="h-[250px] w-full flex items-center justify-center text-sm text-zinc-500">
              {t('trend.noData')}
            </div>
          ) : (
            <div className="h-[250px] w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <XAxis
                    dataKey="timeLabel"
                    stroke="#888888"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    minTickGap={30}
                  />
                  <YAxis
                    stroke="#888888"
                    fontSize={11}
                    tickLine={false}
                    axisLine={false}
                    domain={[0, 100]}
                    tickFormatter={(value) => `${value}%`}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (active && payload && payload.length) {
                        const data = payload[0].payload as ProcessedDataPoint;
                        return (
                          <div className="rounded-lg border bg-background p-3 shadow-md max-w-[240px]">
                            <div className="grid grid-cols-2 gap-2">
                              <div className="flex flex-col">
                                <span className="text-[0.70rem] uppercase text-muted-foreground">
                                  {t('trend.tooltip.time')}
                                </span>
                                <span className="font-bold text-muted-foreground text-xs">{data.fullTime}</span>
                              </div>
                              <div className="flex flex-col items-end">
                                <span className="text-[0.70rem] uppercase text-muted-foreground">
                                  {t('trend.tooltip.score')}
                                </span>
                                <span
                                  className={cn(
                                    'font-bold',
                                    data.status === 'pass'
                                      ? 'text-emerald-500'
                                      : data.status === 'fail'
                                        ? 'text-rose-500'
                                        : 'text-amber-500',
                                  )}
                                >
                                  {data.score}%
                                </span>
                              </div>
                            </div>
                            <p className="text-[10px] text-zinc-500 mt-2 text-center bg-zinc-100 dark:bg-zinc-800 rounded py-1">
                              {t('trend.tooltip.clickHint')}
                            </p>
                          </div>
                        );
                      }
                      return null;
                    }}
                    cursor={{ stroke: 'var(--border)', strokeWidth: 1, strokeDasharray: '4 4' }}
                  />
                  <Line
                    type="monotone"
                    dataKey="score"
                    stroke="#8b5cf6"
                    strokeWidth={2}
                    dot={<CustomDot />}
                    activeDot={{ r: 6, strokeWidth: 0, fill: 'var(--foreground)' }}
                    animationDuration={1000}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{t('trend.modal.title')}</DialogTitle>
            <DialogDescription>
              {selectedPoint && (
                <span className="flex items-center gap-2 mt-1">
                  <span className="font-medium">{selectedPoint.fullTime}</span>
                  <span className="text-zinc-300 dark:text-zinc-700">•</span>
                  <span>
                    {t('trend.modal.score')}: {selectedPoint.score}%
                  </span>
                  <span className="text-zinc-300 dark:text-zinc-700">•</span>
                  <span>
                    {t('trend.modal.totalComponents')}:{' '}
                    {(selectedPoint.harness?.length || 0) + (selectedPoint.server?.length || 0)}
                  </span>
                </span>
              )}
            </DialogDescription>
          </DialogHeader>

          {selectedPoint && (
            <div className="space-y-6 mt-4">
              {selectedPoint.harness && selectedPoint.harness.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold flex items-center gap-2 pb-2 border-b">
                    <span className="flex items-center gap-1">
                      <PackageIcon className="w-4 h-4" /> Harness Framework Layer
                    </span>
                    <Badge variant="secondary" className="text-[10px]">
                      {selectedPoint.harness.length} {t('trend.modal.components')}
                    </Badge>
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {selectedPoint.harness.map(renderReportItem)}
                  </div>
                </div>
              )}
              {selectedPoint.server && selectedPoint.server.length > 0 && (
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold flex items-center gap-2 pb-2 border-b">
                    <span className="flex items-center gap-1">
                      <ServerIcon className="w-4 h-4" /> Server Business Layer
                    </span>
                    <Badge variant="secondary" className="text-[10px]">
                      {selectedPoint.server.length} {t('trend.modal.components')}
                    </Badge>
                  </h3>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    {selectedPoint.server.map(renderReportItem)}
                  </div>
                </div>
              )}
              {!selectedPoint.harness?.length && !selectedPoint.server?.length && (
                <div className="py-8 text-center text-zinc-500 text-sm">{t('trend.modal.noDetails')}</div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
