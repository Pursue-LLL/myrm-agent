export type BatchStatusFilter = 'all' | 'active' | 'pending' | 'running' | 'completed' | 'cancelled' | 'failure';

export type BatchTaskStatus = 'pending' | 'running' | 'completed' | 'cancelled' | 'failure';

export interface BatchTaskListItem {
  batch_id: string;
  skill_ids: { ids: string[] };
  status: string;
  priority: number;
  max_concurrent: number;
  total_tasks: number;
  completed_tasks: number;
  failed_tasks: number;
  cancelled_tasks: number;
  total_execution_time: number;
  total_token_consumption: number;
  estimated_completion_time: string | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
}

export interface BatchAuditLogItem {
  operation: string;
  status: string;
  details: Record<string, unknown>;
  created_at: string;
}

export interface BatchTaskDetailItem extends BatchTaskListItem {
  error_message: string | null;
  audit_logs: BatchAuditLogItem[];
}

export interface BatchTaskStats {
  totalBatches: number;
  activeBatches: number;
  pendingBatches: number;
  runningBatches: number;
  completedBatches: number;
  cancelledBatches: number;
  failedBatches: number;
  totalSkills: number;
  totalTasks: number;
  completedTasks: number;
  failedTasks: number;
  totalTokens: number;
  totalExecutionSeconds: number;
  overallProgress: number;
  averageExecutionSeconds: number;
}

const SKILL_ID_SPLIT_PATTERN = /[\s,;，；]+/u;

export const normalizeBatchStatus = (status: string): BatchTaskStatus => {
  const normalized = status.trim().toLowerCase();

  if (normalized === 'success') {
    return 'completed';
  }

  if (normalized === 'failed' || normalized === 'error') {
    return 'failure';
  }

  if (
    normalized === 'pending' ||
    normalized === 'running' ||
    normalized === 'completed' ||
    normalized === 'cancelled' ||
    normalized === 'failure'
  ) {
    return normalized;
  }

  return 'pending';
};

export const isBatchActiveStatus = (status: string): boolean => {
  const normalized = normalizeBatchStatus(status);
  return normalized === 'pending' || normalized === 'running';
};

export const isBatchTerminalStatus = (status: string): boolean => {
  const normalized = normalizeBatchStatus(status);
  return normalized === 'completed' || normalized === 'cancelled' || normalized === 'failure';
};

export const parseSkillIds = (value: string): string[] => {
  const uniqueIds = new Set<string>();

  for (const part of value.split(SKILL_ID_SPLIT_PATTERN)) {
    const skillId = part.trim();
    if (skillId) {
      uniqueIds.add(skillId);
    }
  }

  return Array.from(uniqueIds);
};

export const getBatchProgress = (completedTasks: number, totalTasks: number): number => {
  if (totalTasks <= 0) {
    return 0;
  }

  return Math.min(100, Math.round((completedTasks / totalTasks) * 100));
};

export const formatDurationSeconds = (durationSeconds: number): string => {
  const safeDuration = Math.max(0, durationSeconds);

  if (safeDuration < 60) {
    return `${safeDuration.toFixed(1)}s`;
  }

  if (safeDuration < 3600) {
    return `${(safeDuration / 60).toFixed(1)}m`;
  }

  return `${(safeDuration / 3600).toFixed(1)}h`;
};

export const formatTokenCount = (count: number): string => {
  return new Intl.NumberFormat('en-US').format(count);
};

export const formatDateTime = (dateString: string | null): string => {
  if (!dateString) {
    return 'N/A';
  }

  return new Date(dateString).toLocaleString();
};

export const formatDuration = (startString: string | null, endString: string | null): string => {
  if (!startString) {
    return 'N/A';
  }

  const start = new Date(startString).getTime();
  const end = endString ? new Date(endString).getTime() : Date.now();
  return formatDurationSeconds((end - start) / 1000);
};

export const buildBatchTaskStats = (tasks: BatchTaskListItem[]): BatchTaskStats => {
  const initialStats: BatchTaskStats = {
    totalBatches: tasks.length,
    activeBatches: 0,
    pendingBatches: 0,
    runningBatches: 0,
    completedBatches: 0,
    cancelledBatches: 0,
    failedBatches: 0,
    totalSkills: 0,
    totalTasks: 0,
    completedTasks: 0,
    failedTasks: 0,
    totalTokens: 0,
    totalExecutionSeconds: 0,
    overallProgress: 0,
    averageExecutionSeconds: 0,
  };

  if (tasks.length === 0) {
    return initialStats;
  }

  let totalSkills = 0;
  let totalTasks = 0;
  let completedTasks = 0;
  let failedTasks = 0;
  let totalTokens = 0;
  let totalExecutionSeconds = 0;
  let pendingBatches = 0;
  let runningBatches = 0;
  let completedBatches = 0;
  let cancelledBatches = 0;
  let failedBatches = 0;

  for (const task of tasks) {
    const normalizedStatus = normalizeBatchStatus(task.status);

    totalSkills += task.skill_ids.ids.length;
    totalTasks += task.total_tasks;
    completedTasks += task.completed_tasks;
    failedTasks += task.failed_tasks;
    totalTokens += task.total_token_consumption;
    totalExecutionSeconds += task.total_execution_time;

    if (normalizedStatus === 'pending') {
      pendingBatches += 1;
    } else if (normalizedStatus === 'running') {
      runningBatches += 1;
    } else if (normalizedStatus === 'completed') {
      completedBatches += 1;
    } else if (normalizedStatus === 'cancelled') {
      cancelledBatches += 1;
    } else if (normalizedStatus === 'failure') {
      failedBatches += 1;
    }
  }

  return {
    totalBatches: tasks.length,
    activeBatches: pendingBatches + runningBatches,
    pendingBatches,
    runningBatches,
    completedBatches,
    cancelledBatches,
    failedBatches,
    totalSkills,
    totalTasks,
    completedTasks,
    failedTasks,
    totalTokens,
    totalExecutionSeconds,
    overallProgress: getBatchProgress(completedTasks, totalTasks),
    averageExecutionSeconds: totalExecutionSeconds / tasks.length,
  };
};

export const matchesBatchStatusFilter = (status: string, filter: BatchStatusFilter): boolean => {
  if (filter === 'all') {
    return true;
  }

  const normalized = normalizeBatchStatus(status);

  if (filter === 'active') {
    return normalized === 'pending' || normalized === 'running';
  }

  return normalized === filter;
};
