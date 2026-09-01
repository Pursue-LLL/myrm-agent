/**
 * [INPUT]
 * ../artifacts::Artifact (POS: 聊天工件契约)
 * ../sources::Source (POS: 消息引用来源与 citation 契约)
 * ../tokens::TokenUsage (POS: Token 用量与经济学快照)
 *
 * [OUTPUT]
 * AgentEventType, BaseAgentEvent, 核心 SSE 事件接口（消息/工具前半）。
 *
 * [POS]
 * SSE 事件类型前半段；与后端 AgentEventType 对齐。
 */

import type { Artifact } from '../artifacts';
import type { RecoveryAction } from '../progress';
import type { Source } from '../sources';
import type { TokenUsage } from '../tokens';
// ---------------------------------------------------------------------------
// SSE 事件类型系统（与后端 AgentEventType StrEnum 对齐）
// ---------------------------------------------------------------------------

export const AgentEventType = {
  ERROR: 'error',
  AGENT_CANCELLED: 'agent_cancelled',
  TASKS_STEPS: 'tasks_steps',
  TOOL_HEARTBEAT: 'tool_heartbeat',
  SOURCES: 'sources',
  MESSAGE: 'message',
  MESSAGE_END: 'message_end',
  ARTIFACTS: 'artifacts',
  ARTIFACT_FOCUS: 'artifact_focus',
  ARTIFACT_CONTENT: 'artifact_content',
  UI_UPDATE: 'ui_update',
  TOOL_START: 'tool_start',
  TOOL_END: 'tool_end',
  TOOL_FAILURE: 'tool_failure',
  TOOL_STDOUT_CHUNK: 'tool_stdout_chunk',
  TOOL_EVICTED_REF: 'tool_evicted_ref',
  TOOL_CANCELLED: 'tool_cancelled',
  TOKEN_USAGE: 'token_usage',
  TOOL_APPROVAL_REQUEST: 'tool_approval_request',
  APPROVAL_REQUIRED: 'approval_required',
  CLARIFICATION_REQUIRED: 'clarification_required',
  DIRECTORY_REQUEST_REQUIRED: 'directory_request_required',
  APPROVAL_PROCESSED: 'approval_processed',
  GOAL_STATUS: 'goal_status',
  RATE_LIMIT_UPDATED: 'rate_limit_updated',
  RATE_LIMIT_WARNING: 'rate_limit_warning',
  RATE_LIMIT_THROTTLED: 'rate_limit_throttled',
  SUBAGENT_STATUS_UPDATE: 'subagent_status_update',
  CATCHUP_SNAPSHOT: 'catchup_snapshot',
  MEMORY_BRIEF: 'memory_brief',
  REASONING: 'reasoning',
  STATUS: 'status',
  TOOLS_SNAPSHOT: 'tools_snapshot',
  ROUTING_DECISION: 'routing_decision',
  PRIVACY_LEVEL: 'privacy_level',
  PRIVACY_ROUTE: 'privacy_route',
  SUBAGENT_START: 'subagent_start',
  SUBAGENT_PROGRESS: 'subagent_progress',
  SUBAGENT_LOG: 'subagent_log',
  SUBAGENT_COMPLETION: 'subagent_completion',
  SUBAGENT_STALE: 'subagent_stale',
  TEAMMATE_MESSAGE: 'teammate_message',
  FILE_DIFF: 'file_diff',
  ITERATION_LIMIT_REACHED: 'iteration_limit_reached',
  CONTEXT_OVERFLOW_RESET: 'context_overflow_reset',
  STEERING: 'steering',
  REDIRECTED: 'redirected',
  TOOL_FALLBACK: 'tool_fallback',
  CONTEXT_REFERENCE_WARNING: 'context_reference_warning',
  CAPTCHA_DETECTED: 'captcha_detected',
  CAPTCHA_RESOLVED: 'captcha_resolved',
  CAPTCHA_TIMEOUT: 'captcha_timeout',
  MODEL_ESCALATED: 'model_escalated',
  MODEL_FAILOVER: 'model_failover',
  MODEL_RECOVERY: 'model_recovery',
  FILE_MUTATION_FAILED: 'file_mutation_failed',
  WORKSPACE_MERGE_FAILED: 'workspace_merge_failed',
  MASCOT_XP_UPDATE: 'mascot_xp_update',
  DAG_STATE_UPDATE: 'dag_state_update',
  TOOL_IMAGE_OUTPUT: 'tool_image_output',
  BROWSER_VIEW_UPDATE: 'browser_view_update',
  DESKTOP_VIEW_UPDATE: 'desktop_view_update',
  DESKTOP_CONTROL_APPROVAL_REQUEST: 'desktop_control_approval_request',
  PTC_NOTIFY: 'ptc_notify',
  TOOL_PROGRESS: 'tool_progress',
  FISSION_TOPOLOGY: 'fission_topology',
  BROWSER_TAKEOVER_REQUESTED: 'browser_takeover_requested',
  BROWSER_TAKEOVER_COMPLETED: 'browser_takeover_completed',
  SESSION_RECORDING: 'session_recording',
  RISK_BLOCKED: 'risk_blocked',
  CORRECTION_LEARNED: 'correction_learned',
  VERIFICATION_VERDICT: 'verification_verdict',
  COUNCIL_PHASE: 'council_phase',
  CAPABILITY_GAP: 'capability_gap',
  SKILL_GAP: 'skill_gap',
} as const;

export interface BaseAgentEvent {
  messageId: string;
}

export type ErrorKind =
  | 'context_overflow'
  | 'rate_limit'
  | 'overloaded'
  | 'billing'
  | 'timeout'
  | 'auth'
  | 'session_expired'
  | 'model_not_found'
  | 'format_error'
  | 'safety_block'
  | 'response_format_error'
  | 'concurrency_limit'
  | 'unknown';

export interface DiagnosticResult {
  error_type: string;
  user_message: string;
  resolution_steps: string[];
  locale: string;
}

export interface ErrorStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.ERROR;
  error?: string;
  data?: string;
  metadata?: Record<string, unknown>;
  error_kind?: ErrorKind;
  retry_after_ms?: number;
  cooldown_remaining_ms?: number;
  recovery_actions?: RecoveryAction[];
  default_hint?: string;
  diagnostic_result?: DiagnosticResult;
  /** Deterministic fault-side attribution (harness FaultSide token). */
  fault_side?: string;
}

export interface RateLimitUpdatedStreamEvent {
  type: 'rate_limit_updated';
  messageId?: string;
}

export interface RateLimitWarningStreamEvent {
  type: 'rate_limit_warning';
  messageId?: string;
  data: {
    provider: string;
    model: string;
    usage_pct: number;
  };
}

export interface RateLimitThrottledStreamEvent {
  type: 'rate_limit_throttled';
  messageId?: string;
  data: {
    wait_seconds: number;
  };
}

export interface AgentCancelledStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.AGENT_CANCELLED;
  data?: { reason?: string };
}

export interface TasksStepsStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TASKS_STEPS;
  step_key: string;
  parent_step_key?: string;
  is_plan?: boolean;
  tool_name?: string;
  tool_call_id?: string;
  agent_instance?: string;
  display_name?: string;
  theme_color?: string;
  data: Array<{ text: string }>;
  count?: number;
  status?: string;
  error?: string;
  error_category?: string;
  error_hint?: string;
  recovery_actions?: RecoveryAction[];
  /** Deterministic fault-side attribution (harness FaultSide token). */
  fault_side?: string;
  progress_percent?: number;
  completed_count?: number;
  failed_count?: number;
  partial_success?: boolean;
  duration_ms?: number;
  metadata?: Record<string, unknown>;
}

export interface ToolHeartbeatStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_HEARTBEAT;
  step_key: string;
  tool_name: string;
  tool_call_id: string;
  elapsed_ms: number;
}

export interface SourcesStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.SOURCES;
  data: Source[];
}

export interface ToolApprovalRequestStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_APPROVAL_REQUEST;
  data: {
    // Standard LangChain HITL structure
    actionRequests: Array<{
      action: string;
      args: Record<string, unknown>;
      description: string;
      domains?: string[];
      ptc_annotations?: Record<string, boolean>;
    }>;
    reviewConfigs: Array<{
      allowedDecisions: Array<'approve' | 'reject' | 'edit'>;
      domainApproval?: boolean;
      smartDenied?: boolean;
      hideAllowAlways?: boolean;
    }>;
    // Extensions (custom fields)
    extensions: {
      timeout: {
        seconds: number;
        expiresAt: number;
        behavior: 'deny' | 'allow';
      };
      approval: {
        requestId: string;
        sessionKey: string;
        permissionType: string;
        allowAlways: boolean;
      };
      displayMode: 'approval' | 'handover';
    };
  };
}

export interface ApprovalProcessedStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.APPROVAL_PROCESSED;
  decision: 'approve' | 'reject' | 'approve_always' | 'feedback';
}

export interface ApprovalRequiredStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.APPROVAL_REQUIRED;
  data: {
    type: string;
    message?: string;
    [key: string]: unknown;
  };
}

export interface ClarificationRequiredWireData {
  type: 'ask_question';
  form: unknown;
}

export interface ClarificationRequiredStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.CLARIFICATION_REQUIRED;
  data: ClarificationRequiredWireData;
}

export interface DirectoryRequestRequiredStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.DIRECTORY_REQUEST_REQUIRED;
  data: {
    request?: {
      reason?: string;
      path?: string;
      writable?: boolean;
    };
    [key: string]: unknown;
  };
}

export interface SteeringStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.STEERING;
  data?: { count?: number; messages?: string[] } | string;
}

export interface RedirectedStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.REDIRECTED;
  data?: string;
}

export interface ArtifactFocusStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.ARTIFACT_FOCUS;
  data?: {
    short_file_id?: string;
    path?: string;
  };
}

export interface RiskBlockedStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.RISK_BLOCKED;
  data?: {
    message: string;
    rules?: Array<{ rule_id: string; display_name: string; severity: string }>;
  };
}

export interface SessionRecordingStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.SESSION_RECORDING;
  data?: {
    filename?: string;
    preview_url?: string;
    content_type?: string;
  };
}

export interface ToolStartStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_START;
  /** LLM 工具调用检测路径不携带 tool_name，预执行钩子路径必带，故为可选。 */
  tool_name?: string;
}

export interface ToolEndStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_END;
  tool_name: string;
  /** MCP 工具视图事件（mcp/agent.py）不含 duration_ms，普通工具事件才携带，故为可选。 */
  duration_ms?: number;
  /** MCP Apps（ext-apps）视图元数据，仅 MCP 工具视图事件携带。 */
  mcp_app?: {
    resource_uri: string;
    server_name?: string;
    structured_content?: Record<string, unknown>;
  };
  result?: unknown;
  cited_memory_ids?: string[];
  cited_memory_refs?: unknown[];
  /** 记忆检索 trace（内存召回工具事件携带，服务端 stream_collector 透传）。 */
  memory_retrieval_trace?: {
    degraded?: boolean;
    id?: string;
  };
}

export interface ToolFailureStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_FAILURE;
  tool_name: string;
  /** 与后端 ToolCallEventData.duration_ms 可选契约对齐，防御未来缺省。 */
  duration_ms?: number;
  error: string;
  /** Deterministic fault-side attribution (harness FaultSide token). */
  fault_side?: string;
}

export interface ToolStdoutChunkStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_STDOUT_CHUNK;
  data: string;
}

export interface ToolCancelledStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_CANCELLED;
  tool_name: string;
  /** 与后端 ToolCallEventData.duration_ms 可选契约对齐，防御未来缺省。 */
  duration_ms?: number;
  error: string;
  cancel_reason?: string; // "user_cancelled" | "timeout" | "session_ended" | "unknown"
}

export interface TokenUsageStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOKEN_USAGE;
  data: { usage: TokenUsage };
}

export interface MessageStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.MESSAGE;
  data: string;
  metadata?: Record<string, unknown>;
}

export interface ArtifactsStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.ARTIFACTS;
  data: Artifact[];
}

export interface ArtifactContentStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.ARTIFACT_CONTENT;
  subtype: 'start' | 'chunk' | 'complete' | 'end';
  artifactId?: string;
  content?: string;
  filename?: string;
  artifactType?: string;
  language?: string;
  artifact?: Artifact;
}

export interface UIUpdateStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.UI_UPDATE;
  subtype: 'ui_artifact' | 'data_update';
  /** `ui_artifact` 分支为 UIArtifact[]；`data_update` 分支为 { surface_id, updates } 对象。由 handler 运行时守卫区分。 */
  data: unknown;
}

export interface CorrectionLearnedStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.CORRECTION_LEARNED;
  summaries?: string[];
  data?: {
    summaries?: string[];
  };
}

export interface ToolEvictedRefStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_EVICTED_REF;
  data: unknown;
}

export interface CapabilityGapStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.CAPABILITY_GAP;
  data?: {
    tool_id?: string;
    tool_group?: string;
  };
}

export interface SkillGapStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.SKILL_GAP;
  data?: {
    skill_id?: string;
  };
}
