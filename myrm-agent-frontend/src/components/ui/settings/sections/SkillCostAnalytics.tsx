'use client';

import { useState, useMemo, useEffect } from 'react';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';

interface CostDataPoint {
  date: string;
  total_cost: number;
  skill_id: string;
}

interface SkillCostAnalyticsProps {
  apiBaseUrl?: string;
}

const TIME_RANGES = [
  { value: '7d', label: 'Last 7 Days' },
  { value: '30d', label: 'Last 30 Days' },
  { value: '90d', label: 'Last 90 Days' },
  { value: 'all', label: 'All Time' },
] as const;

/**
 * Skill成本分析Dashboard
 *
 * P0-1: 可视化LLM成本支出，支持：
 * - 成本趋势图（折线图）
 * - 按Skill排名（柱状图）
 * - 时间范围筛选
 */
export function SkillCostAnalytics({ apiBaseUrl = '/api' }: SkillCostAnalyticsProps) {
  const [timeRange, setTimeRange] = useState<'7d' | '30d' | '90d' | 'all'>('7d');
  const [costData, setCostData] = useState<CostDataPoint[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchCostData();
  }, [timeRange]);

  const fetchCostData = async () => {
    setIsLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${apiBaseUrl}/skill-optimization/cost-analytics?time_range=${timeRange}&group_by=day`,
      );

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      setCostData(data.by_day || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  };

  const { totalCost, topSkills, trendData } = useMemo(() => {
    if (!costData.length) {
      return { totalCost: 0, topSkills: [], trendData: [] };
    }

    // 计算总成本
    const total = costData.reduce((sum, item) => sum + item.total_cost, 0);

    // 按Skill聚合成本
    const skillCosts: Record<string, number> = {};
    costData.forEach((item) => {
      skillCosts[item.skill_id] = (skillCosts[item.skill_id] || 0) + item.total_cost;
    });

    // 按成本排序取Top 10
    const topSkillsList = Object.entries(skillCosts)
      .map(([skill_id, cost]) => ({ skill_id, cost }))
      .sort((a, b) => b.cost - a.cost)
      .slice(0, 10);

    // 趋势数据（按日期聚合）
    const dateCosts: Record<string, number> = {};
    costData.forEach((item) => {
      dateCosts[item.date] = (dateCosts[item.date] || 0) + item.total_cost;
    });

    const trend = Object.entries(dateCosts)
      .map(([date, cost]) => ({ date, cost }))
      .sort((a, b) => a.date.localeCompare(b.date));

    return { totalCost: total, topSkills: topSkillsList, trendData: trend };
  }, [costData]);

  const maxCost = Math.max(...topSkills.map((s) => s.cost), 1);

  return (
    <div className="space-y-4">
      {/* 头部控制 */}
      <div className="flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-foreground">LLM Cost Analytics</h3>
          <p className="text-sm text-muted-foreground">Track optimization costs and identify expensive skills</p>
        </div>

        <div className="flex items-center gap-2">
          {TIME_RANGES.map((range) => (
            <Button
              key={range.value}
              size="sm"
              variant={timeRange === range.value ? 'default' : 'outline'}
              onClick={() => setTimeRange(range.value)}
              disabled={isLoading}
            >
              {range.label}
            </Button>
          ))}
        </div>
      </div>

      {error && (
        <Card className="p-4 border-destructive bg-destructive/10">
          <p className="text-sm text-destructive">Error: {error}</p>
        </Card>
      )}

      {/* 总成本卡片 */}
      <Card className="p-6">
        <div className="text-center">
          <p className="text-sm text-muted-foreground mb-2">Total LLM Cost</p>
          <p className="text-4xl font-bold text-foreground">${totalCost.toFixed(2)}</p>
          <p className="text-xs text-muted-foreground mt-1">
            {timeRange === '7d' && 'Last 7 days'}
            {timeRange === '30d' && 'Last 30 days'}
            {timeRange === '90d' && 'Last 90 days'}
            {timeRange === 'all' && 'All time'}
          </p>
        </div>
      </Card>

      {/* 成本趋势图 */}
      <Card className="p-6">
        <h4 className="text-sm font-semibold text-foreground mb-4">Cost Trend</h4>

        {isLoading ? (
          <div className="h-48 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">Loading...</p>
          </div>
        ) : trendData.length === 0 ? (
          <div className="h-48 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">No data available</p>
          </div>
        ) : (
          <div className="h-48 relative">
            <svg viewBox="0 0 800 200" className="w-full h-full">
              {/* 坐标轴 */}
              <line x1="40" y1="180" x2="780" y2="180" stroke="currentColor" strokeWidth="1" opacity="0.2" />
              <line x1="40" y1="10" x2="40" y2="180" stroke="currentColor" strokeWidth="1" opacity="0.2" />

              {/* 趋势折线 */}
              <polyline
                fill="none"
                stroke="hsl(var(--primary))"
                strokeWidth="2"
                points={trendData
                  .map((point, index) => {
                    const x = 40 + (index / (trendData.length - 1)) * 740;
                    const y = 180 - (point.cost / Math.max(...trendData.map((p) => p.cost))) * 160;
                    return `${x},${y}`;
                  })
                  .join(' ')}
              />

              {/* 数据点 */}
              {trendData.map((point, index) => {
                const x = 40 + (index / (trendData.length - 1)) * 740;
                const y = 180 - (point.cost / Math.max(...trendData.map((p) => p.cost))) * 160;

                return (
                  <g key={point.date}>
                    <circle cx={x} cy={y} r="4" fill="hsl(var(--primary))" />
                    {index % Math.ceil(trendData.length / 6) === 0 && (
                      <text x={x} y="195" fontSize="10" fill="currentColor" opacity="0.6" textAnchor="middle">
                        {point.date.slice(5)}
                      </text>
                    )}
                  </g>
                );
              })}
            </svg>
          </div>
        )}
      </Card>

      {/* Top Skill排名 */}
      <Card className="p-6">
        <h4 className="text-sm font-semibold text-foreground mb-4">Top 10 Most Expensive Skills</h4>

        {isLoading ? (
          <div className="h-48 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">Loading...</p>
          </div>
        ) : topSkills.length === 0 ? (
          <div className="h-48 flex items-center justify-center">
            <p className="text-sm text-muted-foreground">No data available</p>
          </div>
        ) : (
          <div className="space-y-3">
            {topSkills.map((skill, index) => (
              <div key={skill.skill_id} className="flex items-center gap-3">
                {/* 排名 */}
                <div className="w-6 text-right text-sm font-medium text-muted-foreground">#{index + 1}</div>

                {/* Skill名称 */}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium text-foreground truncate">{skill.skill_id}</p>
                </div>

                {/* 成本条形图 */}
                <div className="w-48 h-6 bg-muted rounded-full overflow-hidden">
                  <div
                    className="h-full bg-primary transition-all"
                    style={{
                      width: `${(skill.cost / maxCost) * 100}%`,
                    }}
                  />
                </div>

                {/* 成本数字 */}
                <div className="w-16 text-right">
                  <p className="text-sm font-semibold text-foreground">${skill.cost.toFixed(2)}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>
    </div>
  );
}
