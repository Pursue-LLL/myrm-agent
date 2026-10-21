/**
 * [INPUT]: Runtime process causality graph, orphan reaper telemetry, and post-mortem archives.
 * [OUTPUT]: Strong TypeScript definitions for AgentRuntimeCausalityCockpit component.
 * [POS]: myrm-agent/myrm-agent-frontend/src/components/features/system-monitor/runtimeZombieReaperTypes.ts
 */

export type ProcessLifecycleStateType =
  | 'running'
  | 'idle'
  | 'crashed'
  | 'terminated'
  | 'orphan'
  | 'deadlocked';

export interface ProcessCausalityNodeItem {
  node_id: string;
  name: string;
  role: string;
  pid: number;
  pgid: number;
  parent_id?: string | null;
  profile_id: string;
  state: ProcessLifecycleStateType;
  cpu_percent: number;
  memory_rss_mb: number;
  tokens_consumed: number;
  last_heartbeat_ms: number;
  exit_code?: number | null;
  crash_reason?: string | null;
}

export interface ProfileResourceUsageItem {
  profile_id: string;
  active_processes: number;
  total_cpu_percent: number;
  total_memory_rss_mb: number;
  total_tokens_consumed: number;
}

export interface PostMortemTaskEntryItem {
  task_id: string;
  name: string;
  parent_task_id?: string | null;
  profile_id: string;
  exit_code: number;
  crash_reason: string;
  duration_ms: number;
  terminated_at_ms: number;
}

export interface RuntimeCausalitySnapshotItem {
  nodes: ProcessCausalityNodeItem[];
  profile_summaries: ProfileResourceUsageItem[];
  recent_failed_tasks: PostMortemTaskEntryItem[];
  total_reaped_orphans: number;
  total_deadlocks_broken: number;
  timestamp_ms: number;
}

export interface AgentRuntimeCausalityCockpitProps {
  snapshot: RuntimeCausalitySnapshotItem;
  onReapOrphans?: (parentId: string) => Promise<void> | void;
  onRefresh?: () => Promise<void> | void;
  isLoading?: boolean;
}
