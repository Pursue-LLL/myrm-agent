'use client';

import { useState, useEffect } from 'react';
import { useLocale } from 'next-intl';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/primitives/card';
import { Loader2, Activity, CheckCircle, XCircle, Clock, AlertTriangle } from 'lucide-react';
import { Badge } from '@/components/primitives/badge';
import { Progress } from '@/components/primitives/progress';
import { localizeReactNode } from '@/lib/utils/localeText';

interface BashExecutionStats {
  total_commands: number;
  success_rate: number;
  avg_duration_ms: number;
  error_top10: Array<[string, number]>;
  command_hotmap: Array<[string, number]>;
  type_distribution: Record<string, number>;
  hourly_breakdown: Array<[number, number]>;
}

const StatsDashboard = () => {
  const locale = useLocale();
  const [stats, setStats] = useState<BashExecutionStats | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStats();
  }, []);

  const fetchStats = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/v1/audit/bash/stats');
      if (!response.ok) throw new Error('Failed to fetch stats');

      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error('Error fetching stats:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="size-6 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!stats) {
    return (
      <Card>
        <CardContent className="py-20 text-center text-muted-foreground">
          Failed to load statistics / 加载统计数据失败
        </CardContent>
      </Card>
    );
  }

  const maxHourlyCount = Math.max(...stats.hourly_breakdown.map(([_, count]) => count), 1);

  return localizeReactNode(
    <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
      {/* Overview Stats */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Total Commands / 总命令数</CardTitle>
          <Activity className="size-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.total_commands}</div>
          <p className="text-xs text-muted-foreground">All executed commands / 所有已执行命令</p>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Success Rate / 成功率</CardTitle>
          <CheckCircle className="size-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{(stats.success_rate * 100).toFixed(1)}%</div>
          <Progress value={stats.success_rate * 100} className="mt-2" />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
          <CardTitle className="text-sm font-medium">Avg Duration / 平均耗时</CardTitle>
          <Clock className="size-4 text-muted-foreground" />
        </CardHeader>
        <CardContent>
          <div className="text-2xl font-bold">{stats.avg_duration_ms.toFixed(0)}ms</div>
          <p className="text-xs text-muted-foreground">Average execution time / 平均执行时间</p>
        </CardContent>
      </Card>

      {/* Command Type Distribution */}
      <Card className="md:col-span-2">
        <CardHeader>
          <CardTitle>Command Type Distribution / 命令类型分布</CardTitle>
          <CardDescription>Breakdown by command type / 按命令类型分类</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {Object.entries(stats.type_distribution)
              .sort(([, a], [, b]) => b - a)
              .map(([type, count]) => {
                const percentage = (count / stats.total_commands) * 100;
                return (
                  <div key={type} className="space-y-2">
                    <div className="flex items-center justify-between text-sm">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline">{type}</Badge>
                        <span className="text-muted-foreground">{count} commands</span>
                      </div>
                      <span className="font-medium">{percentage.toFixed(1)}%</span>
                    </div>
                    <Progress value={percentage} />
                  </div>
                );
              })}
          </div>
        </CardContent>
      </Card>

      {/* Command Hotmap */}
      <Card className="md:col-span-2 lg:col-span-1">
        <CardHeader>
          <CardTitle>Top Commands / 热门命令</CardTitle>
          <CardDescription>Most frequently executed / 执行最频繁</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {stats.command_hotmap.slice(0, 5).map(([command, count], index) => (
              <div key={index} className="flex items-center justify-between">
                <span className="truncate font-mono text-sm">{command}</span>
                <Badge variant="secondary">{count}</Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Error Top 10 */}
      <Card className="md:col-span-2">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <XCircle className="size-5 text-destructive" />
            Top Errors / 常见错误
          </CardTitle>
          <CardDescription>Most common error messages / 最常见的错误消息</CardDescription>
        </CardHeader>
        <CardContent>
          {stats.error_top10.length === 0 ? (
            <div className="py-10 text-center text-muted-foreground">No errors found / 未发现错误</div>
          ) : (
            <div className="space-y-3">
              {stats.error_top10.slice(0, 5).map(([error, count], index) => (
                <div key={index} className="flex items-start justify-between gap-4">
                  <span className="flex-1 truncate text-sm">{error || 'Unknown error / 未知错误'}</span>
                  <Badge variant="destructive">{count}</Badge>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Hourly Breakdown */}
      <Card className="md:col-span-2 lg:col-span-3">
        <CardHeader>
          <CardTitle>Hourly Activity / 按小时统计</CardTitle>
          <CardDescription>Command execution by hour of day / 按小时统计命令执行</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex h-40 items-end justify-between gap-1">
            {stats.hourly_breakdown.map(([hour, count]) => {
              const heightPercentage = (count / maxHourlyCount) * 100;
              const isAbnormal = hour >= 2 && hour < 6;
              return (
                <div key={hour} className="flex flex-1 flex-col items-center gap-1">
                  <div
                    className={`w-full rounded-t ${
                      isAbnormal ? 'bg-destructive/70' : 'bg-primary'
                    } transition-all hover:opacity-80`}
                    style={{ height: `${heightPercentage}%` }}
                    title={`${hour}:00 - ${count} commands${isAbnormal ? ' (abnormal time / 异常时间)' : ''}`}
                  />
                  <span className="text-xs text-muted-foreground">{hour}</span>
                </div>
              );
            })}
          </div>
          <div className="mt-4 flex items-center gap-2 text-xs text-muted-foreground">
            <AlertTriangle className="size-4 text-destructive" />
            <span>Red bars indicate abnormal hours (2-6 AM) / 红色条表示异常时间（凌晨2-6点）</span>
          </div>
        </CardContent>
      </Card>
    </div>,
    locale,
  );
};

export default StatsDashboard;
