'use client';

import { useEffect, useState } from 'react';
import { useLocale } from 'next-intl';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Button } from '@/components/primitives/button';
import { Input } from '@/components/primitives/input';
import { Badge } from '@/components/primitives/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/primitives/table';
import { Loader2, RefreshCw, TrendingUp, TrendingDown } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from '@/components/features/app-shell/lazy-recharts';
import { localizeReactNode } from '@/lib/utils/localeText';

interface ComparisonData {
  skill_id: string;
  before_quality: number;
  after_quality: number;
  delta_quality: number;
  delta_success_rate: number;
  delta_token_efficiency: number;
  delta_execution_time: number;
  delta_user_satisfaction: number;
  improvement_pct: number;
  is_statistically_significant: boolean;
  p_value: number | null;
}

const SkillOptimizationPage = () => {
  const locale = useLocale();
  const [comparisons, setComparisons] = useState<ComparisonData[]>([]);
  const [loading, setLoading] = useState(false);
  const [skillIdFilter, setSkillIdFilter] = useState('');
  const [beforeDays, setBeforeDays] = useState(60);
  const [afterDays, setAfterDays] = useState(30);

  const fetchComparisons = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams();
      if (skillIdFilter) params.append('skill_id', skillIdFilter);
      params.append('before_range_days', beforeDays.toString());
      params.append('after_range_days', afterDays.toString());

      const { getApiUrl } = await import('@/lib/api');
      const response = await fetch(getApiUrl(`/skill-optimization/comparison?${params.toString()}`));
      if (!response.ok) throw new Error('Failed to fetch comparisons');

      const data = await response.json();
      setComparisons(data.comparisons || []);
    } catch (error) {
      console.error('Error fetching comparisons:', error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchComparisons();
  }, []);

  const getImprovementBadge = (improvement_pct: number, is_significant: boolean) => {
    if (improvement_pct > 0) {
      return (
        <Badge variant="default" className="flex items-center gap-1">
          <TrendingUp className="size-3" />
          {improvement_pct.toFixed(2)}%{is_significant && ' ✓'}
        </Badge>
      );
    } else if (improvement_pct < 0) {
      return (
        <Badge variant="destructive" className="flex items-center gap-1">
          <TrendingDown className="size-3" />
          {Math.abs(improvement_pct).toFixed(2)}%
        </Badge>
      );
    }
    return <Badge variant="secondary">0%</Badge>;
  };

  const chartData = comparisons.map((comp) => ({
    skill_id: comp.skill_id.substring(0, 20),
    before: comp.before_quality,
    after: comp.after_quality,
  }));

  return localizeReactNode(
    <div className="container mx-auto h-full py-6 px-4 md:px-6">
      <div className="mb-6">
        <h1 className="text-3xl font-bold">Skill Quality Optimization / 技能质量优化</h1>
        <p className="text-muted-foreground mt-2">
          Compare skill quality metrics across time periods with statistical significance testing /
          跨时间段对比技能质量指标并进行统计显著性检验
        </p>
      </div>

      {/* Filters */}
      <Card className="mb-6">
        <CardHeader>
          <CardTitle>Comparison Settings / 对比设置</CardTitle>
          <CardDescription>Configure time ranges and skill filters / 配置时间范围和技能过滤</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Skill ID Filter / 技能ID过滤</label>
              <Input
                placeholder="Optional / 可选"
                value={skillIdFilter}
                onChange={(e) => setSkillIdFilter(e.target.value)}
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Before Range (days) / 前期天数</label>
              <Input type="number" value={beforeDays} onChange={(e) => setBeforeDays(parseInt(e.target.value) || 60)} />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">After Range (days) / 后期天数</label>
              <Input type="number" value={afterDays} onChange={(e) => setAfterDays(parseInt(e.target.value) || 30)} />
            </div>
            <div className="flex items-end">
              <Button onClick={fetchComparisons} disabled={loading} className="w-full">
                {loading ? <Loader2 className="mr-2 size-4 animate-spin" /> : <RefreshCw className="mr-2 size-4" />}
                Compare / 对比
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Chart Visualization */}
      {comparisons.length > 0 && (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Quality Trend Visualization / 质量趋势可视化</CardTitle>
            <CardDescription>Before vs. After quality scores / 前后质量分数对比</CardDescription>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData.slice(0, 10)}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="skill_id" angle={-45} textAnchor="end" height={100} />
                <YAxis domain={[0, 1]} />
                <Tooltip />
                <Legend />
                <Bar dataKey="before" fill="#94a3b8" name="Before / 前" />
                <Bar dataKey="after" fill="#10b981" name="After / 后" />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* Comparison Table */}
      <Card>
        <CardHeader>
          <CardTitle>Comparison Results / 对比结果</CardTitle>
          <CardDescription>
            Detailed metrics comparison with statistical significance / 详细指标对比及统计显著性
          </CardDescription>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="size-8 animate-spin" />
            </div>
          ) : comparisons.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              No comparison data available. Click "Compare" to load data. / 无对比数据。点击"对比"加载数据。
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Skill ID / 技能ID</TableHead>
                    <TableHead className="text-right">Before Quality / 前期质量</TableHead>
                    <TableHead className="text-right">After Quality / 后期质量</TableHead>
                    <TableHead className="text-right">Δ Quality / 质量变化</TableHead>
                    <TableHead className="text-right">Δ Success / 成功率</TableHead>
                    <TableHead className="text-right">Δ Token Eff. / 令牌效率</TableHead>
                    <TableHead className="text-right">Δ Exec Time / 执行时间</TableHead>
                    <TableHead className="text-right">Δ Satisfaction / 满意度</TableHead>
                    <TableHead className="text-right">Improvement / 改进</TableHead>
                    <TableHead className="text-center">Significant / 显著性</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {comparisons.map((comp) => (
                    <TableRow key={comp.skill_id}>
                      <TableCell className="font-mono text-sm max-w-[200px] truncate" title={comp.skill_id}>
                        {comp.skill_id}
                      </TableCell>
                      <TableCell className="text-right">{comp.before_quality.toFixed(3)}</TableCell>
                      <TableCell className="text-right">{comp.after_quality.toFixed(3)}</TableCell>
                      <TableCell className="text-right">
                        <span
                          className={
                            comp.delta_quality > 0 ? 'text-green-600' : comp.delta_quality < 0 ? 'text-red-600' : ''
                          }
                        >
                          {comp.delta_quality > 0 ? '+' : ''}
                          {comp.delta_quality.toFixed(3)}
                        </span>
                      </TableCell>
                      <TableCell className="text-right">
                        {comp.delta_success_rate > 0 ? '+' : ''}
                        {comp.delta_success_rate.toFixed(3)}
                      </TableCell>
                      <TableCell className="text-right">
                        {comp.delta_token_efficiency > 0 ? '+' : ''}
                        {comp.delta_token_efficiency.toFixed(3)}
                      </TableCell>
                      <TableCell className="text-right">
                        {comp.delta_execution_time > 0 ? '+' : ''}
                        {comp.delta_execution_time.toFixed(3)}
                      </TableCell>
                      <TableCell className="text-right">
                        {comp.delta_user_satisfaction > 0 ? '+' : ''}
                        {comp.delta_user_satisfaction.toFixed(3)}
                      </TableCell>
                      <TableCell className="text-right">
                        {getImprovementBadge(comp.improvement_pct, comp.is_statistically_significant)}
                      </TableCell>
                      <TableCell className="text-center">
                        {comp.is_statistically_significant ? (
                          <Badge variant="default">
                            Yes / 是{comp.p_value !== null && ` (p=${comp.p_value.toFixed(4)})`}
                          </Badge>
                        ) : (
                          <Badge variant="secondary">No / 否</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>,
    locale,
  );
};

export default SkillOptimizationPage;
