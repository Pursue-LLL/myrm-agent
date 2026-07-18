/**
 * [INPUT]
 * ./part1::AgentEventType, BaseAgentEvent (POS: SSE 事件类型前半段)
 * ../contextMetrics::ContextBudget (POS: 成本与上下文预算指标类型)
 * 
 * [OUTPUT]
 * Goal/Subagent/Privacy/RateLimit 等 SSE 事件接口。
 * 
 * [POS]
 * SSE 事件类型中段。
 */

import { AgentEventType } from './part1';
import type { BaseAgentEvent, ErrorKind } from './part1';
import type { CompletionStatus } from '../toolApproval';
import type { ProgressItem } from '../progress';
import type { Source } from '../sources';
import type { TokenEconomicsSnapshot, TokenUsage } from '../tokens';
import type { ContextBudget, CostStatus } from '../contextMetrics';

export interface MemoryBriefData {
  snapshot_id: string;
  generated_at_ms: number;
  namespaces: string[];
  is_cold_start: boolean;
  stable: {
    working_state: boolean;
    profile_keys: string[];
    instruction_count: number;
    rule_count: number;
  };
  learned: {
    preference_count: number;
    rule_count: number;
    correction_count: number;
    preference_ids: string[];
    rule_ids: string[];
  };
}

export interface MemoryBriefStatus {
  state: 'ready' | 'skipped';
  reason?: 'timeout' | 'error';
  injection?: MemoryBriefInjectionStatus;
}

export interface MemoryBriefInjectionStatus {
  state: 'applied' | 'not_applied';
  source?: 'snapshot' | 'fallback';
  reason?:
    | 'missing_context'
    | 'not_injected'
    | 'recall_mode_tools'
    | 'load_error'
    | 'static_error'
    | 'invalid_static_payload'
    | 'empty_context'
    | 'already_present';
}

export interface MemoryBriefStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.MEMORY_BRIEF;
  data: MemoryBriefData;
}

export interface GoalBudgetPayload {
  max_tokens?: number;
  max_usd?: number;
  max_time_seconds?: number;
  max_turns?: number;
  convergence_window?: number;
  loop_on_pause?: boolean;
  max_loop_restarts?: number;
}

export interface GoalStatusPayload {
  goal_id: string;
  objective: string;
  ui_summary?: string;
  status: import('@/components/features/chat-window/goals/GoalStatusCard').GoalStatus;
  tokens_used: number;
  time_used_seconds: number;
  cost_usd?: number;
  turns_used?: number;
  no_progress_streak?: number;
  loop_restarts?: number;
  budget?: GoalBudgetPayload;
  verdict?: string;
  reason?: string;
  should_continue?: boolean;
  constraints?: string[];
  acceptance_criteria?: { type: string; command?: string; criteria?: string }[];
  subgoals?: { text: string }[];
  metadata?: {
    execution_summary?: {
      files_modified: string[];
      verifications: { cmd: string; passed: boolean }[];
      browser_checks: number;
      total_tokens: number;
      total_cost_usd: number;
      execution_duration_s: number;
      turns_used: number;
    };
    acceptance_results?: {
      label: string;
      passed: boolean;
      duration_ms: number;
      reason?: string;
      error_logs?: string;
    }[];
    acceptance_history?: {
      timestamp: string;
      results: {
        label: string;
        passed: boolean;
        duration_ms: number;
        reason?: string;
        error_logs?: string;
      }[];
    }[];
    [key: string]: unknown;
  };
}

export interface MessageEndStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.MESSAGE_END;
  usage?: TokenUsage;
  token_economics?: TokenEconomicsSnapshot;
  cost_usd?: number;
  cost_status?: CostStatus;
  completion_status?: CompletionStatus;
  model?: string;
  context_budget?: ContextBudget;
  citations?: string[];
  memoryBudget?: { used: number; total: number };
  memory_brief_snapshot_id?: string;
  memory_brief_status?: MemoryBriefStatus;
  goal_status?: GoalStatusPayload;
  consensus_meta?: {
    models_used: number;
    models_succeeded: number;
    aggregator_model: string;
    elapsed_seconds: number;
  };
}

export interface ReasoningStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.REASONING;
  data: string;
}

export interface StatusStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.STATUS;
  step_key: string;
  data?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  items?: ProgressItem['items'];
  status?: ProgressItem['status'];
  attempt?: number;
  tokens_saved?: number;
  stripped_count?: number;
  tool_name?: string | null;
  error_kind?: ErrorKind;
  fallback_model?: string;
}

export interface CaptchaStreamEvent extends BaseAgentEvent {
  type:
    | typeof AgentEventType.CAPTCHA_DETECTED
    | typeof AgentEventType.CAPTCHA_RESOLVED
    | typeof AgentEventType.CAPTCHA_TIMEOUT;
  data?: {
    reason?: string;
    captcha_type?: string;
  };
}

export interface ModelEscalatedStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.MODEL_ESCALATED;
  data?: {
    from_model?: string;
    to_model?: string;
    reason?: string;
  };
}

export interface ModelFailoverStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.MODEL_FAILOVER;
  data?: {
    fromModel?: string;
    toModel?: string;
    reason?: string;
    errorMessage?: string;
    cooldownMs?: number;
    attemptCount?: number;
    availableCandidates?: string[];
    scenario?: string;
  };
}

export interface ModelRecoveryStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.MODEL_RECOVERY;
  data?: {
    model?: string;
    downtimeMs?: number;
    probeCount?: number;
    wasInCooldown?: boolean;
  };
}

export interface RoutingDecisionStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.ROUTING_DECISION;
  data: {
    tier?: string;
  };
  metadata?: Record<string, unknown>;
}

export interface ToolSnapshotItem {
  name: string;
  summary: string;
  description: string;
  source: string;
  provider: string | null;
  layer: string;
  parameters_schema: Record<string, unknown> | null;
  builtin_tool_id?: string | null;
}

export type SubagentMetadataValue =
  | string
  | number
  | boolean
  | null
  | SubagentMetadataValue[]
  | { [key: string]: SubagentMetadataValue };

export interface ToolsSnapshotStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOLS_SNAPSHOT;
  data: ToolSnapshotItem[];
}

export type SensitivityLevel = 's1' | 's2' | 's3';

export interface PrivacyLevelStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.PRIVACY_LEVEL;
  data: {
    current_turn_level: SensitivityLevel;
    highest_level: SensitivityLevel;
    action?: string;
  };
}

export interface PrivacyRouteStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.PRIVACY_ROUTE;
  data: {
    route?: string;
    level?: string;
  };
}

export interface SubagentStartStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.SUBAGENT_START;
  data: {
    task_id: string;
    parent_task_id?: string;
    agent_type: string;
    description: string;
    role?: string;
    control_scope?: string;
    budget?: Record<string, SubagentMetadataValue>;
  };
}

export interface SubagentProgressStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.SUBAGENT_PROGRESS;
  data: {
    task_id?: string;
    agent_type?: string;
    agent_instance?: string;
    message?: string;
    progress?: number;
    current_tokens?: number;
    budget_tokens?: number;
    tool_count?: number;
    is_estimated?: boolean;
    current_step?: string;
    eta_seconds?: number;
    eta_readable?: string;
  };
}

export interface SubagentLogStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.SUBAGENT_LOG;
  data: {
    task_id?: string;
    agent_type?: string;
    agent_instance?: string;
    level?: string;
    message?: string;
    tool_name?: string | null;
    duration_ms?: number;
    error?: string;
    cancel_reason?: string;
    timeout_seconds?: number;
    attempt?: number;
    max_attempts?: number;
    elapsed_ms?: number;
    backoff_seconds?: number;
    reason?: string;
    reasoning_content?: string;
    step_key?: string;
  };
}

export interface SubagentCompletionStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.SUBAGENT_COMPLETION;
  data: string;
}

export interface SubagentStatusUpdateStreamEvent extends BaseAgentEvent {
  type: 'subagent_status_update';
  data?: {
    task_id?: string;
    status?: string;
    error?: string;
    role?: string;
    control_scope?: string;
    policy_reason?: string;
    policy_details?: string;
    budget?: Record<string, SubagentMetadataValue>;
  };
}

export interface TeammateMessageStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TEAMMATE_MESSAGE;
  data?: {
    message_id?: string;
    from_task_id?: string;
    to_task_id?: string;
    body?: string;
    created_at?: number | string;
  };
}

export interface IterationLimitReachedStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.ITERATION_LIMIT_REACHED;
  data?: {
    limit?: number;
    nodes_completed?: number;
  };
}

export interface ContextOverflowResetStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.CONTEXT_OVERFLOW_RESET;
  data?: {
    chat_id?: string;
  };
}

export interface ToolFallbackStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_FALLBACK;
  tool: string;
  fallback_type: string;
  message: string;
}

export interface ContextReferenceWarningStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.CONTEXT_REFERENCE_WARNING;
  data: {
    message: string;
  };
}

export interface GoalStatusStreamEvent {
  type: typeof AgentEventType.GOAL_STATUS;
  messageId?: string;
  data: GoalStatusPayload;
}

export interface MascotXpUpdateStreamEvent {
  type: typeof AgentEventType.MASCOT_XP_UPDATE;
  messageId?: string;
  data: {
    level: number;
    xp: number;
    next_level_xp: number;
    unlocked_tools: string[];
  };
}

export interface DagStateUpdateStreamEvent {
  type: typeof AgentEventType.DAG_STATE_UPDATE;
  messageId?: string;
  data: unknown;
}

export type { CatchupSnapshotStreamEvent } from './part2Catchup';
