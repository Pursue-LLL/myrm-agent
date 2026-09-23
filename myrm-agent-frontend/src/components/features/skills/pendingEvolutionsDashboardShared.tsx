/**
 * [INPUT]
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind class merge helper)
 * - @/services/skill/growth::SkillGrowthCaseSummary, SkillGrowthSummary (POS: Skill growth REST types)
 *
 * [OUTPUT]
 * - GrowthFilter, FILTER_ORDER, VIEW_MODE_KEY, LIST_CASES_LIMIT, EMPTY_SUMMARY
 * - matchesFilter(), SummaryCard, CapacityPoolBadge, CapacityAlertBanner
 *
 * [POS]
 * Pending evolutions dashboard shared filters and summary card UI extracted for line budget.
 */

import type { ComponentType } from 'react';
import { AlertTriangle, Cpu } from 'lucide-react';
import { cn } from '@/lib/utils/classnameUtils';
import type { SkillGrowthCaseSummary, SkillGrowthSummary } from '@/services/skill/growth';

export type GrowthFilter = 'all' | 'pending' | 'applied' | 'blocked' | 'reviewed';

export const FILTER_ORDER: GrowthFilter[] = ['all', 'pending', 'applied', 'blocked', 'reviewed'];
export const VIEW_MODE_KEY = 'myrm:skill-growth-view-mode';
export const LIST_CASES_LIMIT = 100;

export const EMPTY_SUMMARY: SkillGrowthSummary = {
  total: 0,
  pendingReview: 0,
  autoApplied: 0,
  blocked: 0,
};

export function matchesFilter(item: SkillGrowthCaseSummary, filter: GrowthFilter): boolean {
  if (filter === 'all') {
    return true;
  }
  if (filter === 'pending') {
    return item.status === 'PENDING_REVIEW' || item.status === 'APPLY_FAILED';
  }
  if (filter === 'applied') {
    return item.status === 'AUTO_APPLIED';
  }
  if (filter === 'blocked') {
    return item.status === 'BLOCKED_LOCKED' || item.status === 'FAILED_SCAN';
  }
  return item.status === 'APPROVED' || item.status === 'REJECTED';
}

interface SummaryCardProps {
  icon: ComponentType<{ className?: string }>;
  label: string;
  value: number;
  toneClassName: string;
}

export function SummaryCard({ icon: Icon, label, value, toneClassName }: SummaryCardProps) {
  return (
    <div className="rounded-2xl border bg-background p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="space-y-1">
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="text-2xl font-semibold text-foreground">{value}</p>
        </div>
        <div className={cn('rounded-2xl border p-2.5', toneClassName)}>
          <Icon className="h-5 w-5" />
        </div>
      </div>
    </div>
  );
}

interface CapacityVisualProps {
  skillCount: number;
  maxSkillCount: number;
  capacityPercent: number;
  isWarning: boolean;
  isLimit: boolean;
}

export function CapacityPoolBadge({
  skillCount,
  maxSkillCount,
  capacityPercent,
  isWarning,
  isLimit,
}: CapacityVisualProps) {
  return (
    <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border/50 bg-secondary/30 text-xs">
      <Cpu className="w-3.5 h-3.5 text-muted-foreground" />
      <span className="text-muted-foreground">容量池:</span>
      <span
        className={cn(
          'font-medium font-mono',
          isLimit
            ? 'text-rose-600 dark:text-rose-400 font-semibold'
            : isWarning
              ? 'text-amber-600 dark:text-amber-400 font-semibold'
              : 'text-emerald-600 dark:text-emerald-400'
        )}
      >
        {skillCount}/{maxSkillCount} ({capacityPercent}%)
      </span>
    </div>
  );
}

export function CapacityAlertBanner({
  skillCount,
  maxSkillCount,
  capacityPercent,
  isWarning,
  isLimit,
}: CapacityVisualProps) {
  if (!isWarning && !isLimit) {
    return null;
  }

  return (
    <div
      className={cn(
        'flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-3.5 rounded-xl border backdrop-blur-sm transition-all',
        isLimit
          ? 'border-rose-300/80 bg-rose-50/70 dark:border-rose-900/60 dark:bg-rose-950/20 text-rose-900 dark:text-rose-200'
          : 'border-amber-300/80 bg-amber-50/70 dark:border-amber-900/60 dark:bg-amber-950/20 text-amber-900 dark:text-amber-200'
      )}
    >
      <div className="flex items-start gap-3">
        <AlertTriangle
          className={cn(
            'w-4 h-4 shrink-0 mt-0.5',
            isLimit ? 'text-rose-600 dark:text-rose-400' : 'text-amber-600 dark:text-amber-400'
          )}
        />
        <div className="space-y-0.5 text-xs">
          <div className="font-semibold flex items-center gap-2">
            <span>{isLimit ? '技能自进化已触碰硬限熔断 (100%)' : '技能池接近容量安全阈值 (80%)'}</span>
            <span className="px-1.5 py-0.2 rounded bg-background/60 border border-current font-mono text-[10px]">
              {skillCount}/{maxSkillCount} ({capacityPercent}%)
            </span>
          </div>
          <p className="opacity-90 leading-relaxed">
            {isLimit
              ? '已暂停新技能自动捕获以保护系统提示词预算（Bug修复自愈不受影响）。建议前往技能库归档冷门技能以恢复容量。'
              : '已习得技能数接近上限。建议主动检查并停用长期未调用的冷门技能，防止会话上下文膨胀。'}
          </p>
        </div>
      </div>
    </div>
  );
}
