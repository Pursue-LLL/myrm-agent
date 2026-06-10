import type { TaskStatus, TaskPriority } from '@/services/kanban';

export const NEXT_STATUSES: Partial<Record<TaskStatus, TaskStatus[]>> = {
  triage: ['archived'],
  backlog: ['ready'],
  ready: ['running', 'blocked', 'archived'],
  running: ['completed', 'failed', 'blocked'],
  blocked: ['ready'],
  completed: ['archived'],
  failed: ['ready', 'archived'],
};

export const OUTCOME_STYLES: Record<string, string> = {
  completed: 'text-chart-2',
  blocked: 'text-chart-5',
  crashed: 'text-destructive',
  timed_out: 'text-chart-5',
  reclaimed: 'text-muted-foreground',
};

export const EVENT_KIND_STYLES: Record<string, string> = {
  created: 'bg-primary/20 text-primary',
  claimed: 'bg-chart-4/20 text-chart-4',
  completed: 'bg-chart-2/20 text-chart-2',
  failed: 'bg-destructive/20 text-destructive',
  blocked: 'bg-chart-5/20 text-chart-5',
  unblocked: 'bg-primary/20 text-primary',
  retrying: 'bg-chart-4/20 text-chart-4',
  promoted: 'bg-chart-2/20 text-chart-2',
  reclaimed: 'bg-muted text-muted-foreground',
  archived: 'bg-muted text-muted-foreground',
  heartbeat: 'bg-chart-4/10 text-chart-4',
  user_comment: 'bg-primary/10 text-primary',
  verification_failed: 'bg-chart-5/20 text-chart-5',
  branch_switched: 'bg-blue-500/20 text-blue-500',
  specified: 'bg-purple-500/20 text-purple-500',
  decomposed: 'bg-blue-500/20 text-blue-500',
  timed_out: 'bg-chart-5/20 text-chart-5',
  edited: 'bg-chart-4/20 text-chart-4',
};

export const PRIORITY_INDICATORS: Record<TaskPriority, string> = {
  urgent: 'bg-destructive',
  high: 'bg-chart-5',
  normal: 'bg-primary',
  low: 'bg-muted-foreground/50',
};

export const PRIORITY_STYLES: Record<TaskPriority, string> = {
  urgent: 'bg-destructive/10 text-destructive border-destructive/20',
  high: 'bg-chart-5/10 text-chart-5 border-chart-5/20',
  normal: 'bg-primary/10 text-primary border-primary/20',
  low: 'bg-muted text-muted-foreground border-muted-foreground/20',
};

export const STATUS_DOT: Record<string, string> = {
  triage: 'bg-purple-500',
  completed: 'bg-chart-2',
  failed: 'bg-destructive',
  running: 'bg-chart-4',
  ready: 'bg-primary',
  backlog: 'bg-muted-foreground/50',
  blocked: 'bg-chart-5',
  archived: 'bg-muted-foreground/30',
};

export const DIAGNOSTIC_SEVERITY_STYLES: Record<string, { badge: string; text: string }> = {
  critical: {
    badge: 'bg-destructive/10 text-destructive border-destructive/20',
    text: 'text-destructive',
  },
  error: {
    badge: 'bg-chart-5/10 text-chart-5 border-chart-5/20',
    text: 'text-chart-5',
  },
  warning: {
    badge: 'bg-chart-4/10 text-chart-4 border-chart-4/20',
    text: 'text-chart-4',
  },
};

export const TIMEOUT_PRESETS = [
  { value: 60, labelKey: 'timeout1m' },
  { value: 300, labelKey: 'timeout5m' },
  { value: 600, labelKey: 'timeout10m' },
  { value: 1800, labelKey: 'timeout30m' },
  { value: 3600, labelKey: 'timeout1h' },
  { value: 7200, labelKey: 'timeout2h' },
  { value: 86400, labelKey: 'timeout24h' },
] as const;

export interface TaskDepInfo {
  task_id: string;
  title: string;
  status: TaskStatus;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '-';
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return m > 0 ? `${h}h${m}m` : `${h}h`;
}

export function formatTime(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}
