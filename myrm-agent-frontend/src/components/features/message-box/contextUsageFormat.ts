/**
 * [INPUT]
 * - services/contextHealth::ContextHealth, HealthStatus (POS: Statistics context-health DTO layer.)
 *
 * [OUTPUT]
 * - STATUS_DOT_COLORS: background class per strategy health status.
 * - formatTokens: compact K / M token count.
 * - getTextColorByUsage: text colour tier of a usage percentage.
 * - budgetStatusToHealth: per-turn budget health mapped onto the strategy health scale.
 * - resolveDisplayStatus: strategy health, with an idle-but-working strategy shown as healthy.
 *
 * [POS]
 * Pure display helpers shared by the context usage ring, its tooltip and the strategy panel.
 */

import type { ContextHealth, HealthStatus } from '@/services/contextHealth';

export const STATUS_DOT_COLORS: Record<HealthStatus, string> = {
  inactive: 'bg-muted-foreground/40',
  healthy: 'bg-emerald-500',
  warning: 'bg-amber-500',
  critical: 'bg-rose-500',
};

export function formatTokens(tokens: number): string {
  if (tokens >= 1000000) {
    return `${(tokens / 1000000).toFixed(1)}M`;
  }
  if (tokens >= 1000) {
    return `${(tokens / 1000).toFixed(1)}K`;
  }
  return tokens.toString();
}

export function getTextColorByUsage(percentage: number): string {
  if (percentage >= 90) {
    return 'text-red-500';
  }
  if (percentage >= 75) {
    return 'text-amber-500';
  }
  return 'text-primary-dark';
}

type BudgetHealthStatus = 'healthy' | 'warning' | 'critical';

export function budgetStatusToHealth(status: BudgetHealthStatus | undefined): HealthStatus {
  if (!status) {
    return 'inactive';
  }
  return status;
}

export function resolveDisplayStatus(health: ContextHealth | null): HealthStatus {
  if (!health) {
    return 'inactive';
  }
  if (health.status !== 'inactive') {
    return health.status;
  }
  const { compaction, pruning } = health;
  if ((compaction.active && compaction.count > 0) || (pruning.active && pruning.archived > 0)) {
    return 'healthy';
  }
  return 'inactive';
}
