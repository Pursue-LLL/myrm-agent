'use client';

import { useEffect, useEffectEvent, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { apiRequest } from '@/lib/api';
import { useToast } from '@/hooks/shared/useToast';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from '@/components/features/app-shell/lazy-recharts';

// The theme defines no success / warning colours. Opaque 600 shades keep each line at 3:1 or better
// against the card in both themes.
const SUCCESS_COLOR = 'var(--color-emerald-600, #059669)';
const WARNING_COLOR = 'var(--color-amber-600, #d97706)';

// Axis labels and evolution markers are matched by this string, so both must be formatted by the same function.
const formatTrendDate = (value: string, locale: string): string =>
  new Date(value).toLocaleDateString(locale, { month: 'short', day: 'numeric' });

interface TrendDataPoint {
  timestamp: string;
  avg_quality_score: number;
  avg_success_rate: number;
  avg_token_efficiency?: number;
  execution_count: number;
}

interface EvolutionEvent {
  date: string;
  skill_name?: string;
  before_score?: number | null;
}

interface TrendsData {
  skill_id?: string;
  data_points: TrendDataPoint[];
  evolution_events?: EvolutionEvent[];
  time_range_days: number;
  interval_hours?: number;
}

interface SkillQualityTrendChartProps {
  skillId?: string;
  timeRange?: number;
  autoRefresh?: boolean;
  refreshInterval?: number;
}

export function SkillQualityTrendChart({
  skillId,
  timeRange = 30,
  autoRefresh = false,
  refreshInterval = 60000,
}: SkillQualityTrendChartProps) {
  const t = useTranslations('settings.skillAggregation');
  const locale = useLocale();
  const { toast } = useToast();

  const [trendsData, setTrendsData] = useState<TrendsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTimeRange, setSelectedTimeRange] = useState(timeRange);

  // Refetch on range/skill/refresh changes only, using the latest fetch closure.
  const refreshTrends = useEffectEvent(() => fetchTrends());
  useEffect(() => {
    refreshTrends();

    if (autoRefresh) {
      let timeoutId: NodeJS.Timeout;
      const handleSseEvent = () => {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => refreshTrends(), 1000);
      };
      window.addEventListener('skill_quality_updated', handleSseEvent);
      window.addEventListener('app_resync_required', handleSseEvent);
      return () => {
        window.removeEventListener('skill_quality_updated', handleSseEvent);
        window.removeEventListener('app_resync_required', handleSseEvent);
        clearTimeout(timeoutId);
      };
    }
  }, [selectedTimeRange, skillId, autoRefresh, refreshInterval]);

  const fetchTrends = async () => {
    setLoading(true);
    try {
      const endpoint = skillId
        ? `/skill-quality/trends/skill/${skillId}?time_range_days=${selectedTimeRange}`
        : `/skill-quality/trends/global?time_range_days=${selectedTimeRange}`;

      const data = await apiRequest<TrendsData>(endpoint);
      setTrendsData(data);
    } catch (error) {
      console.error('Failed to fetch trends:', error);
      toast({
        title: t('error'),
        description: t('errorFetchingTrends'),
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const formatChartData = () => {
    if (!trendsData?.data_points) {
      return [];
    }

    return trendsData.data_points.map((point) => ({
      date: formatTrendDate(point.timestamp, locale),
      'Quality Score': (point.avg_quality_score * 100).toFixed(1),
      'Success Rate': (point.avg_success_rate * 100).toFixed(1),
      'Token Efficiency': point.avg_token_efficiency ? (point.avg_token_efficiency * 100).toFixed(1) : undefined,
      Executions: point.execution_count,
    }));
  };

  const timeRangeOptions = [
    { label: t('last7Days'), value: 7 },
    { label: t('last30Days'), value: 30 },
    { label: t('last90Days'), value: 90 },
  ];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>{skillId ? `${t('skillTrend')}: ${skillId}` : t('globalTrend')}</CardTitle>
          <div className="flex gap-2">
            {timeRangeOptions.map((option) => (
              <Button
                key={option.value}
                variant={selectedTimeRange === option.value ? 'default' : 'outline'}
                size="sm"
                onClick={() => setSelectedTimeRange(option.value)}
              >
                {option.label}
              </Button>
            ))}
            <Button variant="outline" size="sm" onClick={fetchTrends}>
              {t('refresh')}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center h-[400px]">
            <p className="text-muted-foreground">{t('loading')}</p>
          </div>
        ) : !trendsData?.data_points?.length ? (
          <div className="flex items-center justify-center h-[400px]">
            <p className="text-muted-foreground">{t('noData')}</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={formatChartData()} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" className="text-sm" tick={{ fill: 'currentColor' }} />
              <YAxis domain={[0, 100]} className="text-sm" tick={{ fill: 'currentColor' }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'var(--popover)',
                  border: '1px solid var(--border)',
                  borderRadius: 'var(--radius)',
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="Quality Score"
                stroke="var(--primary)"
                strokeWidth={2}
                dot={{ r: 4 }}
                activeDot={{ r: 6 }}
                name={t('qualityScore')}
              />
              <Line
                type="monotone"
                dataKey="Success Rate"
                stroke={SUCCESS_COLOR}
                strokeWidth={2}
                dot={{ r: 4 }}
                name={t('successRate')}
              />
              {skillId && (
                <Line
                  type="monotone"
                  dataKey="Token Efficiency"
                  stroke={WARNING_COLOR}
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  name={t('tokenEfficiency')}
                />
              )}
              {trendsData?.evolution_events?.map((event, idx) => {
                return (
                  <ReferenceLine
                    key={`evo-${idx}`}
                    x={formatTrendDate(event.date, locale)}
                    stroke="var(--primary)"
                    strokeDasharray="4 2"
                    strokeOpacity={0.6}
                    label={{
                      value: 'E',
                      position: 'top',
                      fill: 'var(--primary)',
                      fontSize: 10,
                      fontWeight: 600,
                    }}
                  />
                );
              })}
            </LineChart>
          </ResponsiveContainer>
        )}

        {trendsData && trendsData.data_points.length > 0 && (
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="flex flex-col">
              <span className="text-sm text-muted-foreground">{t('dataPoints')}</span>
              <span className="text-2xl font-bold">{trendsData.data_points.length}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-sm text-muted-foreground">{t('avgQuality')}</span>
              <span className="text-2xl font-bold">
                {(
                  trendsData.data_points.reduce((sum, p) => sum + p.avg_quality_score, 0) /
                  trendsData.data_points.length
                ).toFixed(2)}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-sm text-muted-foreground">{t('totalExecutions')}</span>
              <span className="text-2xl font-bold">
                {trendsData.data_points.reduce((sum, p) => sum + p.execution_count, 0)}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-sm text-muted-foreground">{t('timeRange')}</span>
              <span className="text-2xl font-bold">{selectedTimeRange}d</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
