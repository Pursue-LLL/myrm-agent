'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { apiRequest } from '@/lib/api';
import { useToast } from '@/hooks/useToast';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from '@/components/features/app-shell/lazy-recharts';

interface TrendDataPoint {
  timestamp: string;
  avg_quality_score: number;
  avg_success_rate: number;
  avg_token_efficiency?: number;
  execution_count: number;
}

interface TrendsData {
  skill_id?: string;
  data_points: TrendDataPoint[];
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
  const { toast } = useToast();

  const [trendsData, setTrendsData] = useState<TrendsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedTimeRange, setSelectedTimeRange] = useState(timeRange);

  useEffect(() => {
    fetchTrends();

    if (autoRefresh) {
      let timeoutId: NodeJS.Timeout;
      const handleSseEvent = () => {
        clearTimeout(timeoutId);
        timeoutId = setTimeout(() => fetchTrends(), 1000);
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
        description: t('errorFetchingTrends') || 'Failed to fetch trend data',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const formatChartData = () => {
    if (!trendsData?.data_points) return [];

    return trendsData.data_points.map((point) => ({
      date: new Date(point.timestamp).toLocaleDateString('zh-CN', {
        month: 'short',
        day: 'numeric',
      }),
      'Quality Score': (point.avg_quality_score * 100).toFixed(1),
      'Success Rate': (point.avg_success_rate * 100).toFixed(1),
      'Token Efficiency': point.avg_token_efficiency ? (point.avg_token_efficiency * 100).toFixed(1) : undefined,
      Executions: point.execution_count,
    }));
  };

  const timeRangeOptions = [
    { label: t('last7Days') || '7天', value: 7 },
    { label: t('last30Days') || '30天', value: 30 },
    { label: t('last90Days') || '90天', value: 90 },
  ];

  return (
    <Card>
      <CardHeader>
        <div className="flex items-center justify-between">
          <CardTitle>
            {skillId ? `${t('skillTrend') || '技能趋势'}: ${skillId}` : t('globalTrend') || '全局质量趋势'}
          </CardTitle>
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
              {t('refresh') || '刷新'}
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent>
        {loading ? (
          <div className="flex items-center justify-center h-[400px]">
            <p className="text-muted-foreground">{t('loading') || '加载中...'}</p>
          </div>
        ) : !trendsData?.data_points?.length ? (
          <div className="flex items-center justify-center h-[400px]">
            <p className="text-muted-foreground">{t('noData') || '暂无数据'}</p>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart data={formatChartData()} margin={{ top: 5, right: 30, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
              <XAxis dataKey="date" className="text-sm" tick={{ fill: 'currentColor' }} />
              <YAxis domain={[0, 100]} className="text-sm" tick={{ fill: 'currentColor' }} />
              <Tooltip
                contentStyle={{
                  backgroundColor: 'hsl(var(--card))',
                  border: '1px solid hsl(var(--border))',
                  borderRadius: 'var(--radius)',
                }}
              />
              <Legend />
              <Line
                type="monotone"
                dataKey="Quality Score"
                stroke="hsl(var(--primary))"
                strokeWidth={2}
                dot={{ r: 4 }}
                activeDot={{ r: 6 }}
                name={t('qualityScore') || '质量分数'}
              />
              <Line
                type="monotone"
                dataKey="Success Rate"
                stroke="hsl(var(--success))"
                strokeWidth={2}
                dot={{ r: 4 }}
                name={t('successRate') || '成功率'}
              />
              {skillId && (
                <Line
                  type="monotone"
                  dataKey="Token Efficiency"
                  stroke="hsl(var(--warning))"
                  strokeWidth={2}
                  dot={{ r: 4 }}
                  name={t('tokenEfficiency') || 'Token效率'}
                />
              )}
            </LineChart>
          </ResponsiveContainer>
        )}

        {trendsData && trendsData.data_points.length > 0 && (
          <div className="mt-4 grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="flex flex-col">
              <span className="text-sm text-muted-foreground">{t('dataPoints') || '数据点数'}</span>
              <span className="text-2xl font-bold">{trendsData.data_points.length}</span>
            </div>
            <div className="flex flex-col">
              <span className="text-sm text-muted-foreground">{t('avgQuality') || '平均质量'}</span>
              <span className="text-2xl font-bold">
                {(
                  trendsData.data_points.reduce((sum, p) => sum + p.avg_quality_score, 0) /
                  trendsData.data_points.length
                ).toFixed(2)}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-sm text-muted-foreground">{t('totalExecutions') || '总执行次数'}</span>
              <span className="text-2xl font-bold">
                {trendsData.data_points.reduce((sum, p) => sum + p.execution_count, 0)}
              </span>
            </div>
            <div className="flex flex-col">
              <span className="text-sm text-muted-foreground">{t('timeRange') || '时间范围'}</span>
              <span className="text-2xl font-bold">{selectedTimeRange}d</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
