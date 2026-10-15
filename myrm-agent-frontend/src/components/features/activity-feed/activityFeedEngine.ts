/**
 * [INPUT]
 * - @/components/features/activity-feed/activityFeedTypes
 *
 * [OUTPUT]
 * - classifyAutonomyTier, computePriorityWeight, sortActivityFeed,
 *   computeEvaporationProgress, getSourceSystemMeta, filterActivityFeed
 *
 * [POS]
 * Pure computation and classification engine for Item 190.
 * Implements two-phase autonomous categorization, priority pinning, and evaporation progress calculations.
 */

import type {
  FeedSourceSystem,
  FeedAutonomyTier,
  FeedPriority,
  ActivityFeedItem,
  ActivityFeedFilter,
  SourceSystemMeta,
} from './activityFeedTypes';

export function classifyAutonomyTier(
  sourceSystem: FeedSourceSystem,
  riskScore: number,
  requiresApproval: boolean,
): FeedAutonomyTier {
  if (requiresApproval || sourceSystem === 'approval' || riskScore >= 0.8) {
    return 'human_decision_required';
  }

  if (riskScore >= 0.4) {
    return 'supervised';
  }

  return 'full_autonomous';
}

export function computePriorityWeight(priority: FeedPriority): number {
  switch (priority) {
    case 'urgent': {
      return 4;
    }
    case 'high': {
      return 3;
    }
    case 'normal': {
      return 2;
    }
    case 'low': {
      return 1;
    }
    default: {
      return 0;
    }
  }
}

export function sortActivityFeed(items: readonly ActivityFeedItem[]): ActivityFeedItem[] {
  return [...items].sort((a, b) => {
    // 1. Human decision required items are strictly pinned to the top
    const isHumanA = a.autonomyTier === 'human_decision_required' && a.status === 'pending_decision';
    const isHumanB = b.autonomyTier === 'human_decision_required' && b.status === 'pending_decision';
    if (isHumanA !== isHumanB) {
      return isHumanA ? -1 : 1;
    }

    // 2. Active tasks precede evaporating tasks
    const isEvaporatingA = a.status === 'evaporating';
    const isEvaporatingB = b.status === 'evaporating';
    if (isEvaporatingA !== isEvaporatingB) {
      return isEvaporatingA ? 1 : -1;
    }

    // 3. Priority weight desc
    const weightA = computePriorityWeight(a.priority);
    const weightB = computePriorityWeight(b.priority);
    if (weightA !== weightB) {
      return weightB - weightA;
    }

    // 4. Timestamp desc
    return b.timestamp - a.timestamp;
  });
}

export function computeEvaporationProgress(
  resolvedAt?: number,
  ttlMs: number = 5000,
  now: number = Date.now(),
): number {
  if (!resolvedAt) {
    return 0;
  }

  const elapsed = now - resolvedAt;
  if (elapsed <= 0) {
    return 0;
  }

  if (elapsed >= ttlMs) {
    return 1;
  }

  return Number((elapsed / ttlMs).toFixed(3));
}

export function getSourceSystemMeta(source: FeedSourceSystem): SourceSystemMeta {
  switch (source) {
    case 'email': {
      return { source, label: '邮件服务', badgeColor: 'indigo' };
    }
    case 'calendar': {
      return { source, label: '日程日历', badgeColor: 'sky' };
    }
    case 'messaging': {
      return { source, label: '即时消息', badgeColor: 'emerald' };
    }
    case 'approval': {
      return { source, label: '审批决断', badgeColor: 'rose' };
    }
    case 'cron': {
      return { source, label: '定时调度', badgeColor: 'purple' };
    }
    case 'kanban': {
      return { source, label: '看板任务', badgeColor: 'amber' };
    }
  }
}

export function filterActivityFeed(
  items: readonly ActivityFeedItem[],
  filter: ActivityFeedFilter,
): ActivityFeedItem[] {
  const query = filter.searchQuery.trim().toLowerCase();

  return items.filter((item) => {
    if (filter.sourceSystem !== 'all' && item.sourceSystem !== filter.sourceSystem) {
      return false;
    }

    if (filter.status !== 'all' && item.status !== filter.status) {
      return false;
    }

    if (filter.onlyHumanRequired && item.autonomyTier !== 'human_decision_required') {
      return false;
    }

    if (query) {
      const matchTitle = item.title.toLowerCase().includes(query);
      const matchSummary = item.summary.toLowerCase().includes(query);
      const matchRef = item.sourceRefId.toLowerCase().includes(query);
      if (!matchTitle && !matchSummary && !matchRef) {
        return false;
      }
    }

    return true;
  });
}
