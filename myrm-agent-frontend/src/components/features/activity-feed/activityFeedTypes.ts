/**
 * [INPUT]
 * - None (Pure domain type definitions for Multi-System Activity Feed & Auto-Evaporating Queue)
 *
 * [OUTPUT]
 * - FeedSourceSystem, FeedItemStatus, FeedAutonomyTier, FeedPriority,
 *   ActivityFeedItem, ActivityFeedFilter, SourceSystemMeta, ActivityFeedStoreState
 *
 * [POS]
 * Unified contract for Item 190: ActivityFeedMultiSystemAggregatorAndAutoEvaporatingQueueSuite.
 * Aggregates multi-source events (Email, Calendar, Messaging, Approvals, Cron, Kanban)
 * and governs two-phase autonomous evaporation vs pinned executive decision bottlenecks.
 */

export type FeedSourceSystem =
  | 'email'
  | 'calendar'
  | 'messaging'
  | 'approval'
  | 'cron'
  | 'kanban';

export type FeedItemStatus =
  | 'pending_decision'
  | 'autonomous_processing'
  | 'evaporating'
  | 'evaporated'
  | 'dismissed';

export type FeedAutonomyTier =
  | 'full_autonomous'
  | 'supervised'
  | 'human_decision_required';

export type FeedPriority = 'urgent' | 'high' | 'normal' | 'low';

export interface ActivityFeedItem {
  readonly id: string;
  readonly sourceSystem: FeedSourceSystem;
  readonly sourceRefId: string;
  readonly title: string;
  readonly summary: string;
  readonly autonomyTier: FeedAutonomyTier;
  readonly status: FeedItemStatus;
  readonly timestamp: number;
  readonly resolvedAt?: number;
  readonly evaporationTtlMs?: number;
  readonly evaporatedAt?: number;
  readonly priority: FeedPriority;
  readonly payloadSnippet?: string;
}

export interface ActivityFeedFilter {
  readonly sourceSystem: FeedSourceSystem | 'all';
  readonly status: FeedItemStatus | 'all';
  readonly onlyHumanRequired: boolean;
  readonly searchQuery: string;
}

export interface SourceSystemMeta {
  readonly source: FeedSourceSystem;
  readonly label: string;
  readonly badgeColor: 'sky' | 'indigo' | 'amber' | 'rose' | 'emerald' | 'purple';
}

export interface ActivityFeedStoreState {
  readonly items: readonly ActivityFeedItem[];
  readonly archive: readonly ActivityFeedItem[];
  readonly filter: ActivityFeedFilter;
  readonly isEvaporationPaused: boolean;
}
