export type TimelineNodeType =
  | 'agent_thought'
  | 'skill_call'
  | 'tool_invocation'
  | 'mcp_call'
  | 'checkpoint'
  | 'system_io';

export type TimelineNodeStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'interrupted';

export interface TimelineIOMetrics {
  input_chars: number;
  output_chars: number;
  prompt_tokens: number | null;
  completion_tokens: number | null;
  cache_hit: boolean;
}

export interface TimelineStepNode {
  node_id: string;
  step_name: string;
  parent_id: string | null;
  step_index: number;
  node_type: TimelineNodeType;
  status: TimelineNodeStatus;
  start_time_ms: number;
  end_time_ms: number | null;
  duration_ms: number | null;
  input_payload: Record<string, string> | null;
  output_payload: Record<string, string> | null;
  metrics: TimelineIOMetrics;
  error_message: string | null;
  children: TimelineStepNode[];
}

export interface TimelineSummaryStats {
  total_steps: number;
  completed_steps: number;
  failed_steps: number;
  running_steps: number;
  interrupted_steps: number;
  total_duration_ms: number;
  total_tokens: number;
}

export interface TimelineInterruption {
  reason: string;
  instruction: string;
}

export interface TaskTimelineData {
  task_id: string;
  tree: TimelineStepNode[];
  waterfall: TimelineStepNode[];
  summary: TimelineSummaryStats;
  interruptions: TimelineInterruption[];
}

export interface TaskInspectorState {
  isOpen: boolean;
  activeTaskId: string | null;
  viewMode: 'tree' | 'waterfall';
  timelineData: TaskTimelineData | null;
  isLoading: boolean;
  isInterrupting: boolean;
  selectedNodeId: string | null;
  expandedNodeIds: string[];
  error: string | null;
  openInspector: (taskId: string) => void;
  closeInspector: () => void;
  setViewMode: (mode: 'tree' | 'waterfall') => void;
  selectNode: (nodeId: string | null) => void;
  toggleExpand: (nodeId: string) => void;
  fetchTimeline: (taskId: string) => Promise<void>;
  interruptTask: (reason?: string, instruction?: string) => Promise<void>;
}
