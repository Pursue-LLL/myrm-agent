'use client';

import { useEffect, useState } from 'react';
import { useLocale, useTranslations } from 'next-intl';
import { Card } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { apiRequest } from '@/lib/api';
import { useToast } from '@/hooks/useToast';
import { localizeReactNode } from '@/lib/utils/localeText';
import { SkillRadarChart } from './SkillRadarChart';
import { QualityTrendChart } from './QualityTrendChart';
import { SkillVersionHistory } from '@/components/settings/SkillVersionHistory';

interface DashboardData {
  active_optimizations: number;
  ab_tests_running: number;
  top_skills: Array<{ skill_id: string; score: number }>;
  bottom_skills: Array<{ skill_id: string; score: number }>;
}

interface QualityScore {
  success_rate: number;
  token_efficiency: number;
  execution_time: number;
  user_satisfaction: number;
  call_frequency: number;
  overall_score: number;
}

export function SkillOptimizationSection() {
  const t = useTranslations('settings.skillOptimization');
  const locale = useLocale();
  const { toast } = useToast();

  const [dashboardData, setDashboardData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedSkill, setSelectedSkill] = useState<string | null>(null);
  const [qualityData, setQualityData] = useState<QualityScore | null>(null);
  const [qualityHistory, setQualityHistory] = useState<any[]>([]);
  const [showTrend, setShowTrend] = useState(false);

  useEffect(() => {
    fetchDashboardData();
  }, []);

  const fetchDashboardData = async () => {
    try {
      setLoading(true);
      const data = await apiRequest<DashboardData>('/skill-optimization/dashboard');
      setDashboardData(data);
    } catch (error) {
      console.error('Failed to fetch dashboard data:', error);
      toast({
        title: 'Error',
        description: 'Failed to load dashboard data',
        variant: 'destructive',
      });
    } finally {
      setLoading(false);
    }
  };

  const fetchQualityData = async (skillId: string) => {
    try {
      const response = await apiRequest<{
        skill_id: string;
        skill_name: string;
        quality_score: QualityScore;
        recommendation: string;
      }>(`/skill-optimization/quality/${skillId}`);
      setQualityData(response.quality_score);
      setSelectedSkill(skillId);

      // 同时获取质量历史数据
      await fetchQualityHistory(skillId);
    } catch (error) {
      console.error('Failed to fetch quality data:', error);
      toast({
        title: 'Error',
        description: 'Failed to load quality data',
        variant: 'destructive',
      });
    }
  };

  const fetchQualityHistory = async (skillId: string) => {
    try {
      const response = await apiRequest<{
        skill_id: string;
        days: number;
        history: any[];
      }>(`/skill-optimization/quality-history/${skillId}?days=30`);
      setQualityHistory(response.history);
    } catch (error) {
      console.error('Failed to fetch quality history:', error);
      // 不阻塞主流程，静默失败
      setQualityHistory([]);
    }
  };

  const triggerOptimization = async (skillId: string) => {
    try {
      await apiRequest(`/skill-optimization/optimize/${skillId}`, {
        method: 'POST',
        body: JSON.stringify({ force: false }),
      });
      toast({
        title: 'Success',
        description: `Optimization triggered for skill ${skillId}`,
      });
      fetchDashboardData();
    } catch (error) {
      console.error('Failed to trigger optimization:', error);
      toast({
        title: 'Error',
        description: 'Failed to trigger optimization',
        variant: 'destructive',
      });
    }
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-2xl font-bold">{t('title')}</h2>
          <p className="text-muted-foreground mt-2">{t('description')}</p>
        </div>
        <Card className="p-6">
          <p className="text-center text-muted-foreground">Loading...</p>
        </Card>
      </div>
    );
  }

  return localizeReactNode(
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold">{t('title')}</h2>
          <p className="text-muted-foreground mt-2">{t('description')}</p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => window.open('/skill-optimization', '_blank', 'noopener,noreferrer')}>
            View Comparison Analysis / 查看对比分析
          </Button>
          <Button variant="default" onClick={() => window.open('/batch-optimization', '_blank', 'noopener,noreferrer')}>
            Batch Optimization / 批量优化
          </Button>
        </div>
      </div>

      {/* Dashboard Stats */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">{t('dashboard')}</h3>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">{t('activeOptimizations')}</p>
            <p className="text-3xl font-bold text-primary">{dashboardData?.active_optimizations || 0}</p>
          </div>
          <div className="space-y-2">
            <p className="text-sm text-muted-foreground">{t('abTestsRunning')}</p>
            <p className="text-3xl font-bold text-primary">{dashboardData?.ab_tests_running || 0}</p>
          </div>
        </div>
      </Card>

      {/* Top Skills */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">{t('topSkills')}</h3>
        {dashboardData && dashboardData.top_skills.length > 0 ? (
          <div className="space-y-3">
            {dashboardData.top_skills.map((skill, index) => (
              <div
                key={skill.skill_id}
                className="flex items-center justify-between p-3 rounded-lg bg-secondary/50 hover:bg-secondary transition-colors cursor-pointer"
                onClick={() => fetchQualityData(skill.skill_id)}
              >
                <div className="flex items-center gap-3">
                  <span className="flex items-center justify-center w-8 h-8 rounded-full bg-primary text-primary-foreground text-sm font-semibold">
                    {index + 1}
                  </span>
                  <span className="font-medium">{skill.skill_id}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-sm text-muted-foreground">
                    {t('qualityScore')}: {(skill.score * 100).toFixed(1)}%
                  </span>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={(e) => {
                      e.stopPropagation();
                      fetchQualityData(skill.skill_id);
                    }}
                  >
                    Details
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t('noData')}</p>
        )}
      </Card>

      {/* Bottom Skills */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">{t('bottomSkills')}</h3>
        {dashboardData && dashboardData.bottom_skills.length > 0 ? (
          <div className="space-y-3">
            {dashboardData.bottom_skills.map((skill) => (
              <div
                key={skill.skill_id}
                className="flex items-center justify-between p-3 rounded-lg bg-destructive/10 hover:bg-destructive/20 transition-colors"
              >
                <div className="flex items-center gap-3">
                  <span className="font-medium">{skill.skill_id}</span>
                  <span className="text-sm text-muted-foreground">
                    {t('qualityScore')}: {(skill.score * 100).toFixed(1)}%
                  </span>
                </div>
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => fetchQualityData(skill.skill_id)}>
                    Details
                  </Button>
                  <Button size="sm" onClick={() => triggerOptimization(skill.skill_id)}>
                    {t('triggerOptimization')}
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-muted-foreground">{t('noData')}</p>
        )}
      </Card>

      {/* Quality Details (if skill selected) */}
      {selectedSkill && qualityData && (
        <Card className="p-6">
          <div className="flex items-center justify-between mb-6">
            <h3 className="text-lg font-semibold">
              {t('qualityScore')}: {selectedSkill}
            </h3>
            <div className="flex gap-2">
              <Button size="sm" variant={showTrend ? 'default' : 'outline'} onClick={() => setShowTrend(!showTrend)}>
                {showTrend ? 'Radar Chart' : 'Trend Chart'}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() => {
                  setSelectedSkill(null);
                  setQualityData(null);
                  setQualityHistory([]);
                  setShowTrend(false);
                }}
              >
                Close
              </Button>
            </div>
          </div>

          {/* Overall Score */}
          <div className="mb-6 p-4 rounded-lg bg-primary/10">
            <p className="text-sm text-muted-foreground mb-2">{t('overallScore')}</p>
            <p className="text-4xl font-bold text-primary">{(qualityData.overall_score * 100).toFixed(1)}%</p>
          </div>

          {/* 雷达图或趋势图切换 */}
          {!showTrend ? (
            <div className="space-y-4">
              <h4 className="font-semibold text-sm text-muted-foreground">5D Quality Radar Chart</h4>

              {/* 雷达图 */}
              <div className="flex justify-center py-4">
                <SkillRadarChart
                  data={[
                    { label: 'Success Rate', value: qualityData.success_rate },
                    { label: 'Token Efficiency', value: qualityData.token_efficiency },
                    { label: 'Execution Time', value: qualityData.execution_time },
                    { label: 'User Satisfaction', value: qualityData.user_satisfaction },
                    { label: 'Call Frequency', value: qualityData.call_frequency },
                  ]}
                  size={300}
                />
              </div>

              {/* 详细指标 */}
              <div className="grid grid-cols-2 gap-4 mt-4">
                <QualityMetricBar label={t('successRate')} value={qualityData.success_rate} />
                <QualityMetricBar label={t('tokenEfficiency')} value={qualityData.token_efficiency} />
                <QualityMetricBar label={t('executionTime')} value={qualityData.execution_time} />
                <QualityMetricBar label={t('userSatisfaction')} value={qualityData.user_satisfaction} />
              </div>
            </div>
          ) : (
            <div className="space-y-4">
              <h4 className="font-semibold text-sm text-muted-foreground">Quality Score Trend (Last 30 Days)</h4>

              {/* 趋势图 */}
              {qualityHistory.length > 0 ? (
                <div className="flex justify-center py-4">
                  <QualityTrendChart
                    data={qualityHistory.map((h) => ({
                      timestamp: h.timestamp,
                      overall_score: h.overall_score,
                    }))}
                    width={700}
                    height={300}
                  />
                </div>
              ) : (
                <p className="text-center text-sm text-muted-foreground py-8">No historical data available</p>
              )}
            </div>
          )}

          {/* Version History */}
          <div className="mt-6 border-t pt-6">
            <SkillVersionHistory skillId={selectedSkill} />
          </div>
        </Card>
      )}

      {/* Actions */}
      <Card className="p-6">
        <h3 className="text-lg font-semibold mb-4">{t('actions')}</h3>
        <div className="flex flex-wrap gap-4">
          <Button variant="outline" onClick={fetchDashboardData}>
            Refresh
          </Button>
          <Button variant="outline">{t('viewHistory')}</Button>
        </div>
      </Card>
    </div>,
    locale,
  );
}

function QualityMetricBar({ label, value }: { label: string; value: number }) {
  const percentage = (value * 100).toFixed(1);
  const barWidth = `${value * 100}%`;

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">{label}</span>
        <span className="text-sm text-muted-foreground">{percentage}%</span>
      </div>
      <div className="h-2 bg-secondary rounded-full overflow-hidden">
        <div className="h-full bg-primary rounded-full transition-all duration-500" style={{ width: barWidth }} />
      </div>
    </div>
  );
}
