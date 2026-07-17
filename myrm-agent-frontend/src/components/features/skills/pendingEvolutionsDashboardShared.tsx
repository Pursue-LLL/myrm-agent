/**
 * [INPUT]
 * - @/lib/utils/classnameUtils::cn (POS: Tailwind class merge helper)
 * - @/services/skill-growth::SkillGrowthCaseSummary, SkillGrowthSummary (POS: Skill growth REST types)
 *
 * [OUTPUT]
 * - GrowthFilter, FILTER_ORDER, VIEW_MODE_KEY, LIST_CASES_LIMIT, EMPTY_SUMMARY
 * - matchesFilter(), SummaryCard
 *
 * [POS]
 * Pending evolutions dashboard shared filters and summary card UI extracted for line budget.
 */

import type { ComponentType } from 'react';
import { cn } from '@/lib/utils/classnameUtils';
import type { SkillGrowthCaseSummary, SkillGrowthSummary } from '@/services/skill-growth';

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
  if (filter === 'all') return true;
  if (filter === 'pending') return item.status === 'PENDING_REVIEW' || item.status === 'APPLY_FAILED';
  if (filter === 'applied') return item.status === 'AUTO_APPLIED';
  if (filter === 'blocked') return item.status === 'BLOCKED_LOCKED' || item.status === 'FAILED_SCAN';
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
