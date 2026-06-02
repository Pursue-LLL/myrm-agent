'use client';

import { useEffect, useState } from 'react';
import { useTranslations } from 'next-intl';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { apiRequest } from '@/lib/api';
import { useToast } from '@/hooks/useToast';
import { QualityDistributionChart } from './QualityDistributionChart';
import { SkillQualityTrendChart } from './SkillQualityTrendChart';

interface GlobalMetrics {
  total_skills: number;
  total_users: number;
  total_executions: number;
  avg_quality_score: number;
  median_quality_score: number;
  quality_std: number;
  top_skills_count: number;
  bottom_skills_count: number;
  optimization_rate: number;
  calculated_at: string;
}

interface SkillAggregate {
  skill_id: string;
  sample_count: number;
  avg_quality_score: number;
  quality_std: number;
  avg_success_rate: number;
  avg_token_efficiency: number;
  avg_execution_time: number;
  avg_user_satisfaction: number;
  total_executions: number;
}

export function GlobalSkillQualityDashboard() {
  const t = useTranslations('settings.skillAggregation');
  const { toast } = useToast();

  const [globalMetrics, setGlobalMetrics] = useState<GlobalMetrics | null>(null);
  const [topSkills, setTopSkills] = useState<SkillAggregate[]>([]);
  const [worstSkills, setWorstSkills] = useState<SkillAggregate[]>([]);
  const [loading, setLoading] = useState(true);
  const [timeRange, setTimeRange] = useState<number>(30);

  useEffect(() => {
    fetchAllData();
  }, [timeRange]);

  const fetchAllData = async () => {
    setLoading(true);
    try {
      await Promise.all([fetchGlobalMetrics(), fetchSkillAggregates()]);
    } finally {
      setLoading(false);
    }
  };

  const fetchGlobalMetrics = async () => {
    try {
      const data = await apiRequest<GlobalMetrics>(`/skill-optimization/global-metrics?time_range_days=${timeRange}`);
      setGlobalMetrics(data);
    } catch (error) {
      console.error('Failed to fetch global metrics:', error);
      toast({
        title: t('error'),
        description: t('errorFetchingMetrics'),
        variant: 'destructive',
      });
    }
  };

  const fetchSkillAggregates = async () => {
    try {
      const response = await apiRequest<{
        aggregates: SkillAggregate[];
        count: number;
      }>(`/skill-optimization/aggregate-by-skill?time_range_days=${timeRange}`);

      const sorted = [...response.aggregates].sort((a, b) => b.avg_quality_score - a.avg_quality_score);

      setTopSkills(sorted.slice(0, 5));
      setWorstSkills(sorted.slice(-5).reverse());
    } catch (error) {
      console.error('Failed to fetch skill aggregates:', error);
    }
  };

  const handleExport = async (format: 'csv' | 'json') => {
    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_BASE_URL || 'http://localhost:8080/api/v1'}/skill-optimization/export?format=${format}&time_range_days=${timeRange}`,
      );

      if (!response.ok) throw new Error('Export failed');

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `skill_quality_aggregates.${format}`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);

      toast({
        title: t('exportSuccess'),
        description: t('exportSuccessDescription'),
      });
    } catch {
      toast({
        title: t('exportFailed'),
        description: t('exportFailedDescription'),
        variant: 'destructive',
      });
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center p-8">
        <div className="text-muted-foreground">{t('loading')}</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold">{t('title')}</h2>
        <div className="flex items-center gap-4">
          <select
            value={timeRange}
            onChange={(e) => setTimeRange(Number(e.target.value))}
            className="px-3 py-2 border rounded-full"
          >
            <option value={7}>{t('last7Days')}</option>
            <option value={30}>{t('last30Days')}</option>
            <option value={90}>{t('last90Days')}</option>
          </select>

          <Button variant="outline" onClick={() => handleExport('csv')}>
            {t('exportCSV')}
          </Button>
          <Button variant="outline" onClick={() => handleExport('json')}>
            {t('exportJSON')}
          </Button>
        </div>
      </div>

      {globalMetrics && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <Card className="p-6">
              <div className="text-sm text-muted-foreground">{t('avgQuality')}</div>
              <div className="text-3xl font-bold mt-2">{(globalMetrics.avg_quality_score * 100).toFixed(1)}%</div>
              <div className="text-xs text-muted-foreground mt-1">
                {t('median')}: {(globalMetrics.median_quality_score * 100).toFixed(1)}%
              </div>
            </Card>

            <Card className="p-6">
              <div className="text-sm text-muted-foreground">{t('totalSkills')}</div>
              <div className="text-3xl font-bold mt-2">{globalMetrics.total_skills}</div>
              <div className="text-xs text-muted-foreground mt-1">
                {t('executions')}: {globalMetrics.total_executions.toLocaleString()}
              </div>
            </Card>

            <Card className="p-6">
              <div className="text-sm text-muted-foreground">{t('optimizationRate')}</div>
              <div className="text-3xl font-bold mt-2">{(globalMetrics.optimization_rate * 100).toFixed(2)}%</div>
              <div className="text-xs text-muted-foreground mt-1">
                {t('topSkills')}: {globalMetrics.top_skills_count} | {t('bottomSkills')}:{' '}
                {globalMetrics.bottom_skills_count}
              </div>
            </Card>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card className="p-6">
              <h3 className="text-lg font-semibold mb-4">{t('qualityDistribution')}</h3>
              <QualityDistributionChart
                excellent={globalMetrics.top_skills_count}
                good={Math.max(
                  0,
                  globalMetrics.total_skills - globalMetrics.top_skills_count - globalMetrics.bottom_skills_count,
                )}
                poor={globalMetrics.bottom_skills_count}
              />
            </Card>

            <Card className="p-6">
              <h3 className="text-lg font-semibold mb-4">{t('topSkills')}</h3>
              <div className="space-y-3">
                {topSkills.map((skill, idx) => (
                  <div key={skill.skill_id} className="flex items-center justify-between">
                    <div className="flex items-center gap-3">
                      <div className="flex items-center justify-center w-6 h-6 rounded-full bg-primary/10 text-primary text-sm font-medium">
                        {idx + 1}
                      </div>
                      <span className="text-sm font-medium">{skill.skill_id}</span>
                    </div>
                    <div className="flex items-center gap-4">
                      <span className="text-xs text-muted-foreground">
                        {skill.total_executions} {t('executions')}
                      </span>
                      <span className="text-sm font-semibold text-green-600">
                        {(skill.avg_quality_score * 100).toFixed(1)}%
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          </div>

          <Card className="p-6">
            <h3 className="text-lg font-semibold mb-4">{t('worstSkills')}</h3>
            <div className="space-y-3">
              {worstSkills.map((skill, idx) => (
                <div key={skill.skill_id} className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <div className="flex items-center justify-center w-6 h-6 rounded-full bg-destructive/10 text-destructive text-sm font-medium">
                      {idx + 1}
                    </div>
                    <span className="text-sm font-medium">{skill.skill_id}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    <span className="text-xs text-muted-foreground">
                      {skill.total_executions} {t('executions')}
                    </span>
                    <span className="text-sm font-semibold text-red-600">
                      {(skill.avg_quality_score * 100).toFixed(1)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </Card>

          <SkillQualityTrendChart timeRange={timeRange} autoRefresh={false} refreshInterval={60000} />
        </>
      )}
    </div>
  );
}
