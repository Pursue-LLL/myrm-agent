/**
 * 跨端统一「需要你」中断队列与可锚定后台告警套件 - 类型契约
 *
 * 覆盖 7 大中断源归并、双写待办台账、离线聚合与可锚定深链规范。
 */

import type { WorkspaceTaskItem } from '../workspaceCockpitTypes';

export type InterruptionSource =
  | 'approval_pending' // 敏感工具/Shell 执行审批
  | 'goal_needs_review' // 目标分解完成待人类评审
  | 'kanban_human_block' // 看板泳道人工阻塞
  | 'commitment_due' // 主动承诺履约到期
  | 'task_failed_retry' // 任务非预期失败待人工仲裁
  | 'budget_threshold' // 算力/Token/计费限额告警
  | 'unattended_clarification'; // 无人值守长程跑动中待答关键问题

export type InterruptionUrgency = 'urgent' | 'normal' | 'low';

export interface NeedsYouItem {
  id: string;
  source: InterruptionSource;
  title: string;
  whyStopped: string;
  whatWaitingFor: string;
  chatId: string;
  messageId?: string;
  turnId?: number;
  agentId?: string;
  agentName?: string;
  createdAt: number;
  urgency: InterruptionUrgency;
  deepLinkUrl: string;
  metadata?: Record<string, string | number | boolean>;
  isDismissed?: boolean;
  dismissReason?: string;
  isHandled?: boolean;
}

export interface AnchoredAlert {
  id: string;
  itemId: string;
  source: InterruptionSource;
  title: string;
  summary: string;
  timestamp: number;
  hasShownSystemNotification: boolean;
  isRead: boolean;
  deepLinkUrl: string;
}

export interface BatchActionPayload {
  itemIds: string[];
  action: 'approve' | 'retry' | 'dismiss';
  reason?: string;
}

export interface NeedsYouQueueSummary {
  totalPendingCount: number;
  urgentCount: number;
  normalCount: number;
  longestWaitingMs: number;
  unreadAlertCount: number;
}

export type NeedsYouTaskItem = WorkspaceTaskItem;
