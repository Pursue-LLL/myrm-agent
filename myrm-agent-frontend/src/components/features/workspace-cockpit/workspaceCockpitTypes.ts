/**
 * [INPUT]
 * None (Pure domain contracts for Workspace Cockpit, 4 Swimlanes, and Offline Digest)
 *
 * [OUTPUT]
 * SwimlaneType, WorkspaceTaskItem, OfflineDigestSummary, WorkspaceManagerCockpitProps
 *
 * [POS]
 * Type contract layer for Personal Workspace Cockpit and Manager Deck. Aligns with LoopX dashboard and Hermes v0.21.5.
 */

export type SwimlaneType = 'needs-you' | 'in-progress' | 'observing' | 'scheduled';

export type TaskExecutionStatus =
  | 'pending'
  | 'running'
  | 'success'
  | 'failed'
  | 'waiting_approval';

export interface WorkspaceTaskItem {
  id: string;
  title: string;
  swimlane: SwimlaneType;
  status: TaskExecutionStatus;
  chatId: string;
  agentId?: string;
  agentName?: string;
  updatedAt: number;
  waitingDurationMs?: number;
  latestOutputTail?: string;
  scheduleCron?: string;
  errorReason?: string;
}

export interface OfflineDigestHighlight {
  id: string;
  title: string;
  type: 'success' | 'failure' | 'decision';
  timeAgo: string;
  chatId: string;
}

export interface OfflineDigestSummary {
  awayDurationMs: number;
  completedGoalsCount: number;
  failedTasksCount: number;
  pendingDecisionsCount: number;
  inProgressCount: number;
  highlights: OfflineDigestHighlight[];
}

export interface WorkspaceManagerCockpitProps {
  tasks: WorkspaceTaskItem[];
  onNavigateToChat: (chatId: string, taskId?: string) => void;
  onApproveDecision?: (taskId: string) => void;
  onRejectDecision?: (taskId: string) => void;
  onRefresh?: () => void;
  lastActiveTimestamp?: number;
  className?: string;
}
