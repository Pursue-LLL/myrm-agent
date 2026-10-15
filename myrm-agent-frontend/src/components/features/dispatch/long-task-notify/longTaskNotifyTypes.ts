export type TaskExecutionEnvironment =
  | 'cloud-server'
  | 'desktop-daemon'
  | 'cluster-pod';

export type TaskRunStatus =
  | 'dispatching'
  | 'running_unattended'
  | 'completed'
  | 'failed'
  | 'paused';

export type PushNotificationChannel = 'web-push' | 'system-toast' | 'webhook';

export interface TaskSourcedChecklistItem {
  id: string;
  title: string;
  sourceUrl: string;
  sourceTitle: string;
  verified: boolean;
  snippet: string;
  timestamp: number;
}

export interface LongTaskDispatchTicket {
  taskId: string;
  title: string;
  prompt: string;
  estimatedDurationSec: number;
  executionEnv: TaskExecutionEnvironment;
  notifyChannels: PushNotificationChannel[];
  startedAt: number;
  completedAt?: number;
  status: TaskRunStatus;
  progressPercent: number;
  currentStep: string;
  sourcedChecklist: TaskSourcedChecklistItem[];
  pushSent: boolean;
}

export interface RejoinSessionContext {
  taskId: string;
  lastSyncTimestamp: number;
  stepsCompleted: number;
  isBackgrounded: boolean;
}
