/**
 * [INPUT]
 * - None (Pure domain type definitions for Attention Hub & Intervention Badge)
 *
 * [OUTPUT]
 * - AttentionPriority, AttentionCategory, AttentionItem, AttentionFilterState,
 *   AttentionCategoryMeta, AttentionHubStoreState
 *
 * [POS]
 * Unified contract for Item 189: AttentionHubNotificationQueueAndInterventionBadgeSuite.
 * Consolidates blocking approvals, clarification cards, failed tasks, and milestone completions
 * into an authoritative multi-task attention hub with priority grading and focus shuttle targets.
 */

export type AttentionPriority = 'urgent' | 'high' | 'medium' | 'info';

export type AttentionCategory =
  | 'approval_blocking'
  | 'clarification_needed'
  | 'task_failed'
  | 'task_completed';

export interface AttentionItem {
  readonly id: string;
  readonly chatId: string;
  readonly chatTitle: string;
  readonly category: AttentionCategory;
  readonly priority: AttentionPriority;
  readonly title: string;
  readonly description: string;
  readonly timestamp: number;
  readonly expiresAt?: number;
  readonly targetAnchorNodeId?: string;
  readonly isRead: boolean;
  readonly actionRequired: boolean;
}

export interface AttentionFilterState {
  readonly category: AttentionCategory | 'all';
  readonly onlyActionRequired: boolean;
  readonly searchQuery: string;
}

export interface AttentionCategoryMeta {
  readonly category: AttentionCategory;
  readonly label: string;
  readonly badgeColor: 'rose' | 'amber' | 'orange' | 'emerald';
}

export interface AttentionHubStoreState {
  readonly items: readonly AttentionItem[];
  readonly isPanelOpen: boolean;
  readonly filter: AttentionFilterState;
}
