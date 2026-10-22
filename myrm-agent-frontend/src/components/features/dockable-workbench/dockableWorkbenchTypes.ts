/**
 * 可停靠上下文工作台与三态绝对一致性类型定义
 * 严禁 any 类型，确保严格 Type Hints 与只读保障
 */

export type DockablePanelId = 'changes' | 'file_preview' | 'live_browser' | 'terminal';

export type DockPosition = 'right' | 'bottom' | 'closed';

export type TriSurfaceMode = 'collapsed_row' | 'expanded_card' | 'detail_drawer';

export type TaskExecutionStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface TriSurfaceTaskState {
  readonly taskId: string;
  readonly status: TaskExecutionStatus;
  readonly currentTool?: string;
  readonly stepIndex: number;
  readonly totalSteps: number;
  readonly epoch: number;
  readonly sequenceNo: number;
  readonly progressPercentage: number;
  readonly lastMessage?: string;
}

export interface FileChangeItem {
  readonly path: string;
  readonly changeType: 'added' | 'modified' | 'deleted';
  readonly additions: number;
  readonly deletions: number;
  readonly diffHunk: string;
}

export interface BootstrapSessionPayload {
  readonly sessionId: string;
  readonly sessionTitle: string;
  readonly activeAgentName: string;
  readonly sandboxChanges: readonly FileChangeItem[];
  readonly eventBaselineEpoch: number;
  readonly initialMessagesCount: number;
  readonly cachedAt: string;
}

export interface DerivedSurfaceView {
  readonly displayStatus: string;
  readonly statusColor: string;
  readonly progressText: string;
  readonly currentActionSummary: string;
  readonly isSynced: boolean;
}
