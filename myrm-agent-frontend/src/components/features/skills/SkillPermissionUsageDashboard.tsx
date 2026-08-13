'use client';

/**
 * Skill Permission Usage Dashboard
 *
 * 展示 Skill 权限使用统计（允许/拒绝比例、最近操作），用于安全审计与异常检测。
 * 入口：技能详情侧边栏 → 「权限使用审计」区块。
 */

import { useLocale, useTranslations } from 'next-intl';
import { useState, useEffect } from 'react';
import {
  BarChart3,
  CheckCircle,
  XCircle,
  Clock,
  TrendingUp,
  AlertCircle,
  FileEdit,
  Terminal,
  Code,
  Globe,
  Variable,
  Trash2,
  FileText,
} from 'lucide-react';

import { cn } from '@/lib/utils/classnameUtils';
import { Card } from '@/components/primitives/card';
import { Badge } from '@/components/primitives/badge';
import { toast } from '@/hooks/shared/useToast';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/primitives/select';

interface PermissionUsageEntry {
  permission: string;
  operation: string;
  allowed: boolean;
  deny_reason: string | null;
  used_at: string;
}

interface PermissionUsageStats {
  permission: string;
  total_count: number;
  allowed_count: number;
  denied_count: number;
  recent_operations: PermissionUsageEntry[];
}

interface SkillPermissionUsage {
  skill_id: string;
  skill_name: string;
  stats: PermissionUsageStats[];
  total_operations: number;
}

interface SkillPermissionUsageDashboardProps {
  skillId: string;
}

const getPermissionIcon = (permission: string) => {
  switch (permission) {
    case 'file_read':
      return FileText;
    case 'file_write':
      return FileEdit;
    case 'file_delete':
      return Trash2;
    case 'shell_exec':
      return Terminal;
    case 'code_interpreter':
      return Code;
    case 'network_access':
      return Globe;
    case 'env_var_access':
      return Variable;
    default:
      return BarChart3;
  }
};

function PermissionStatsCard({ stat }: { stat: PermissionUsageStats }) {
  const t = useTranslations('skills.permissions.usage');
  const locale = useLocale();
  const Icon = getPermissionIcon(stat.permission);
  const successRate = stat.total_count > 0 ? (stat.allowed_count / stat.total_count) * 100 : 0;
  const isHighRisk = stat.denied_count > stat.allowed_count && stat.denied_count > 5;

  return (
    <Card className={cn('p-4', isHighRisk && 'border-yellow-500')}>
      <div className="flex items-start justify-between">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10">
            <Icon className="h-5 w-5 text-primary" />
          </div>
          <div>
            <h4 className="font-semibold">{t(`permLabels.${stat.permission}`, { defaultValue: stat.permission })}</h4>
            <p className="text-xs text-muted-foreground">
              {stat.total_count} {t('totalOps')}
            </p>
          </div>
        </div>
        {isHighRisk && (
          <Badge variant="destructive" className="text-xs">
            <AlertCircle className="mr-1 h-3 w-3" />
            {t('highDenialRate')}
          </Badge>
        )}
      </div>

      <div className="mt-4 grid grid-cols-3 gap-2">
        <div className="text-center">
          <div className="text-2xl font-bold">{stat.total_count}</div>
          <div className="text-xs text-muted-foreground">{t('total')}</div>
        </div>
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 text-2xl font-bold text-green-500">
            <CheckCircle className="h-5 w-5" />
            {stat.allowed_count}
          </div>
          <div className="text-xs text-muted-foreground">{t('allowed')}</div>
        </div>
        <div className="text-center">
          <div className="flex items-center justify-center gap-1 text-2xl font-bold text-red-500">
            <XCircle className="h-5 w-5" />
            {stat.denied_count}
          </div>
          <div className="text-xs text-muted-foreground">{t('denied')}</div>
        </div>
      </div>

      <div className="mt-3">
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{t('successRate')}</span>
          <span>{successRate.toFixed(1)}%</span>
        </div>
        <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted">
          <div className="h-full bg-green-500 transition-all" style={{ width: `${successRate}%` }} />
        </div>
      </div>

      {stat.recent_operations.length > 0 && (
        <div className="mt-4 space-y-2 border-t pt-3">
          <div className="text-xs font-medium text-muted-foreground">{t('recentOps')}</div>
          {stat.recent_operations.slice(0, 3).map((op, idx) => (
            <div
              key={idx}
              className={cn(
                'flex items-start gap-2 rounded-md border p-2 text-xs',
                op.allowed ? 'border-green-500/20 bg-green-500/5' : 'border-red-500/20 bg-red-500/5',
              )}
            >
              {op.allowed ? (
                <CheckCircle className="mt-0.5 h-3 w-3 text-green-500" />
              ) : (
                <XCircle className="mt-0.5 h-3 w-3 text-red-500" />
              )}
              <div className="flex-1">
                <div className="font-mono">{op.operation}</div>
                {op.deny_reason && <div className="mt-0.5 text-xs text-red-600">{op.deny_reason}</div>}
                <div className="mt-1 text-xs text-muted-foreground">
                  <Clock className="mr-1 inline h-3 w-3" />
                  {new Date(op.used_at).toLocaleString(locale)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export function SkillPermissionUsageDashboard({ skillId }: SkillPermissionUsageDashboardProps) {
  const t = useTranslations('skills.permissions.usage');
  const [usage, setUsage] = useState<SkillPermissionUsage | null>(null);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState<number>(7);

  useEffect(() => {
    let cancelled = false;

    const loadUsageStats = async () => {
      setLoading(true);
      try {
        const response = await fetch(`/api/v1/skills/${skillId}/permissions/usage?days=${days}`);
        if (!response.ok) throw new Error('Failed to load usage stats');
        const data = (await response.json()) as SkillPermissionUsage;
        if (!cancelled) setUsage(data);
      } catch (error) {
        console.error('Failed to load usage stats:', error);
        if (!cancelled) {
          toast({
            title: t('error'),
            description: t('loadFailed'),
            variant: 'destructive',
          });
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };

    void loadUsageStats();
    return () => {
      cancelled = true;
    };
  }, [skillId, days, t]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-8">
        <div className="text-sm text-muted-foreground">{t('loading')}</div>
      </div>
    );
  }

  if (!usage || usage.stats.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed py-12">
        <BarChart3 className="h-8 w-8 text-muted-foreground" />
        <div className="text-sm text-muted-foreground">{t('noData')}</div>
      </div>
    );
  }

  const totalAllowed = usage.stats.reduce((sum, s) => sum + s.allowed_count, 0);
  const totalDenied = usage.stats.reduce((sum, s) => sum + s.denied_count, 0);
  const overallSuccessRate = usage.total_operations > 0 ? (totalAllowed / usage.total_operations) * 100 : 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold">
            {t('title')} - {usage.skill_name}
          </h3>
          <div className="mt-2 flex flex-wrap items-center gap-4 text-sm">
            <div className="flex items-center gap-2">
              <BarChart3 className="h-4 w-4 text-muted-foreground" />
              <span className="font-semibold">{usage.total_operations}</span>
              <span className="text-muted-foreground">{t('totalOps')}</span>
            </div>
            <div className="flex items-center gap-2">
              <CheckCircle className="h-4 w-4 text-green-500" />
              <span className="font-semibold text-green-600">{totalAllowed}</span>
              <span className="text-muted-foreground">{t('allowed')}</span>
            </div>
            <div className="flex items-center gap-2">
              <XCircle className="h-4 w-4 text-red-500" />
              <span className="font-semibold text-red-600">{totalDenied}</span>
              <span className="text-muted-foreground">{t('denied')}</span>
            </div>
            <div className="flex items-center gap-2">
              <TrendingUp className="h-4 w-4 text-blue-500" />
              <span className="font-semibold text-blue-600">{overallSuccessRate.toFixed(1)}%</span>
              <span className="text-muted-foreground">{t('successRate')}</span>
            </div>
          </div>
        </div>

        <Select value={days.toString()} onValueChange={(v) => setDays(Number.parseInt(v))}>
          <SelectTrigger className="w-full sm:w-[140px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="1">{t('last1day')}</SelectItem>
            <SelectItem value="7">{t('last7days')}</SelectItem>
            <SelectItem value="30">{t('last30days')}</SelectItem>
            <SelectItem value="90">{t('last90days')}</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {usage.stats.map((stat) => (
          <PermissionStatsCard key={stat.permission} stat={stat} />
        ))}
      </div>
    </div>
  );
}

export default SkillPermissionUsageDashboard;
