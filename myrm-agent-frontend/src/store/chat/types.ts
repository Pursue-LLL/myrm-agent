/**
 * [INPUT]
 * @/store/config/providerTypes::SingleModelSelection (POS: Provider/model selection type contract)
 *
 * [OUTPUT]
 * Chat message, stream event, artifact, memory citation and store state TypeScript contracts.
 *
 * [POS]
 * Chat state and SSE event type definitions. It is the shared contract between stream consumers,
 * message rendering and persisted chat message metadata.
 */

import type { SingleModelSelection } from '@/store/config/providerTypes';

// ---------------------------------------------------------------------------
// 内置工具 ID 常量
// ---------------------------------------------------------------------------

export type BuiltinToolId =
  | 'web_search'
  | 'memory'
  | 'file_ops'
  | 'code_execute'
  | 'wiki'
  | 'browser'
  | 'computer_use'
  | 'image_generation'
  | 'video_generation'
  | 'tts'
  | 'kanban'
  | 'llm_map'
  | 'answer_tool';

export const BUILTIN_TOOL_IDS: readonly BuiltinToolId[] = [
  'web_search',
  'memory',
  'file_ops',
  'code_execute',
  'wiki',
  'browser',
  'computer_use',
  'image_generation',
  'video_generation',
  'tts',
  'kanban',
  'llm_map',
  'answer_tool',
] as const;

export const DEFAULT_ENABLED_BUILTIN_TOOLS: BuiltinToolId[] = ['web_search', 'memory'];

// 外部引用来源类型
export type SourceType = 'web_search' | 'web_fetch' | 'mcp' | 'conversation_history';

// MCP 调用记录
export interface MCPCallRecord {
  tool_name: string; // 工具名称
  result_preview: string; // 返回结果摘要（前500字符）
}

// 外部引用来源数据
export interface Source {
  index: number; // 引用编号（从1开始）
  type: SourceType; // 来源类型
  source_key?: string; // 稳定去重键
  // web_search 和 web_fetch 共有字段
  url?: string; // URL
  title?: string; // 页面标题
  snippet?: string; // 摘要（仅 web_search）
  summary?: string; // 长摘要（会话历史等结构化来源）
  score?: number; // 相关度
  // mcp 技能字段
  skill_name?: string; // 技能名称
  calls?: MCPCallRecord[]; // MCP 调用记录列表
  // knowledge base fields
  kb_name?: string;
  filename?: string;
  section?: string;
  // conversation_history 字段
  conversation_id?: string;
  message_id?: string;
  agent_id?: string;
  surface?: string;
  fork_parent_id?: string;
  lineage?: string;
  created_at?: string;
  updated_at?: string;
}

export interface CitedMemoryReference {
  id: string;
  memoryType?: string;
  content?: string;
  score?: number;
  createdAt?: string;
  primaryNamespace?: string;
  namespaces?: string[];
  sourceChatId?: string;
  sourceMessageId?: string;
}

export interface FileMutationFailure {
  path: string;
  tool: string;
  error_preview: string;
}

// 操作模式类型
export type ActionMode = 'fast' | 'agent' | 'deep_research' | 'consensus' | 'claude_code';

// 快速搜索深度类型
export type SearchDepth = 'normal' | 'deep';

export interface ModelSelection {
  providerId: string;
  model: string;
  baseUrl?: string;
  modelKwargs?: Record<string, unknown>;
  supportsVision?: boolean;
}

// 智能体配置
export interface AgentConfig {
  selectedSkillIds: string[];
  skillConfigs?: Record<string, { is_core?: boolean }>;
  selectedMcpNames: string[];
  systemPrompt: string;
  useGlobalInstruction: boolean;
  autoRestoreDomains?: string[]; // 自动恢复的浏览器身份域名列表
  // 已保存智能体信息（用于追踪和更新）
  agentId?: string;
  agentName?: string;
  agentDescription?: string;
  avatarUrl?: string;
  // 预置智能体信息
  presetId?: string;
  presetName?: string;
  presetIcon?: string;
  modelSelection?: SingleModelSelection | null;
  fallbackModelSelection?: SingleModelSelection | null;
  safetyFallbackModelSelection?: SingleModelSelection | null;
  forceDelegateAgent?: string;
  enabledBuiltinTools?: BuiltinToolId[];
  browserEngine?: string;
  suggestionPrompts?: string[];
  ephemeralSubagents?: Record<string, unknown>;
  taskAdaptiveDigest?: Record<string, unknown>;
  memoryDecayProfile?: 'permanent' | 'normal' | 'fast';
  mcpToolSelections?: Record<string, string[]>;
}

// 已选模型配置
export interface SelectedModels {
  base?: string | null;
  vision?: string | null;
  reasoning?: string | null;
}

export type RecoveryAction = {
  id: string;
  label: string;
  url: string;
};

export type ProgressItem = {
  step_key: string; // 步骤标识符（用于 i18n）
  parent_step_key?: string; // 父步骤标识符（用于树形结构）
  is_plan?: boolean; // 是否为计划节点
  tool_name?: string; // 工具名称（工具调用场景）
  tool_call_id?: string; // 工具调用唯一标识符（用于精准匹配并发心跳）
  reason?: string; // 执行理由（工具调用场景）
  elapsed_ms?: number; // 执行耗时（用于长耗时工具的心跳感知）
  agent_instance?: string; // Agent实例标识（用于Subagent）
  display_name?: string; // Agent自定义显示名称（优先于agent_instance）
  theme_color?: string; // Agent主题颜色（用于视觉区分）
  items?:
    | { text: string }[]
    | { query: string }[]
    | string
    | { url: string }[]
    | { skill_name: string; reason?: string }[] // 技能选择
    | {
        file_path: string;
        line_range?: string;
        action_type?: string;
        size_bytes?: string;
        diff?: string;
        diff_truncated?: boolean;
      }[] // 文件路径（用于 file_editor view）
    | { code: string }[]; // 代码内容（用于 bash_code_execute）
  status?: 'success' | 'error' | 'warning' | 'cancelled'; // 步骤执行状态（warning 用于取消）
  error?: boolean | string; // 错误标记或错误信息
  error_category?: string; // 错误分类（用于显示特殊 Badge，如 OOM, Network Blocked）
  error_hint?: string; // 诊断建议（LLM 友好或用户友好的文字提示）
  // PTC `tools.notify` 内联活动卡字段（同 category 的多次 notify 合并到一个 step）
  notify_message?: string; // 最新一次 notify 的文本
  notify_progress?: number; // 0-100 进度百分比
  notify_step_index?: number; // 当前步骤序号（>=1）
  notify_total_steps?: number; // 总步骤数（>=1）
  notify_level?: 'info' | 'warn' | 'alert'; // notify 等级（用于渲染颜色）
  notify_category?: string; // 业务分类（如 crawl / parse / render）
  recovery_actions?: RecoveryAction[]; // LLM 错误恢复操作按钮
  archive_restore_block?: ArchiveRestoreBlockPayload; // 归档恢复阻断详情，用于聊天流内恢复入口
  archive_restore_actions?: ArchiveRestoreAction[]; // 可直接发送的 typed archive restore actions
  archive_restore_result?: ArchiveRestoreResultPayload; // typed archive restore 恢复结果
  count?: number; // 计数（用于 reviewing_sources 等）
  progress_percent?: number; // 整体进度百分比（0-100）
  duration_ms?: number; // 工具执行耗时（毫秒）
  stdout?: string; // 实时终端输出流（用于 Live Terminal 组件）
};

// Token 使用量统计
export type TokenUsage = {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  cached_tokens?: number;
  cache_write_tokens?: number;
  reasoning_tokens?: number;
  citation_tokens?: number;
};

// Token 经济学快照
export type TokenEconomicsSnapshot = {
  usage: TokenUsage;
  call_count: number;
  total_cost_usd: number;
  total_cache_savings_usd?: number;
  cost_status: CostStatus;
  error_count: number;
  latency: {
    avg_ms: number;
    p95_ms: number;
    min_ms: number;
    max_ms: number;
    avg_ttft_ms: number;
    p95_ttft_ms: number;
    avg_tokens_per_second: number;
  };
  model_breakdown?: Record<string, TokenUsage & { cost_usd: number }>;
  tool_breakdown?: Record<string, TokenUsage & { cost_usd: number }>;
};

// 工件类型
export type ArtifactType =
  | 'code'
  | 'document'
  | 'html'
  | 'pdf'
  | 'image'
  | 'video'
  | 'audio'
  | 'svg'
  | 'mermaid'
  | 'binary'
  | 'interactive_ui';

// 工件版本数据
export interface ArtifactVersion {
  versionId: string; // 版本 ID
  versionNumber: number; // 版本号（从 1 开始）
  content: string; // 版本内容快照
  createdAt: string; // 创建时间
  description?: string; // 版本描述（如 "AI 添加了重置按钮"）
}

// 工件数据
export interface Artifact {
  id: string; // 文件 ID
  filename: string; // 文件名
  type: ArtifactType; // 工件类型
  content_type: string; // MIME 类型
  size: number; // 文件大小（字节）
  preview_url: string; // 预览 URL
  download_url: string; // 下载 URL
  language?: string; // 编程语言（代码类型）
  created_at?: string; // 创建时间
  file_path?: string; // 本地文件路径（仅本地模式）
  // 版本历史
  versions?: ArtifactVersion[]; // 版本历史列表
  currentVersionIndex?: number; // 当前版本索引（默认为最新版本）
}

// ==================== 交互式 UI 类型定义 (A2UI 风格) ====================

// 支持的 UI 组件类型（安全白名单）
export type UIComponentType =
  // 基础组件
  | 'text'
  | 'button'
  | 'button_group'
  // 表单组件
  | 'text_field'
  | 'textarea'
  | 'select'
  | 'date_picker'
  | 'time_picker'
  | 'slider'
  | 'checkbox'
  | 'radio'
  | 'switch'
  // 布局组件
  | 'container'
  | 'card'
  | 'divider'
  | 'grid'
  | 'tabs'
  // 数据展示组件
  | 'table'
  | 'list'
  | 'image'
  | 'chart'
  | 'progress'
  | 'badge';

// UI 组件声明
export interface UIComponent {
  id: string; // 组件唯一标识符
  type: UIComponentType; // 组件类型
  props: Record<string, unknown>; // 组件属性
  children: string[]; // 子组件 ID 列表
  bindings: Record<string, string>; // 数据绑定 (prop -> dataPath)
  events: Record<string, string>; // 事件绑定 (eventName -> actionId)
}

// UI 动作定义
export interface UIAction {
  id: string; // 动作唯一标识符
  type: 'submit' | 'cancel' | 'navigate' | 'custom'; // 动作类型
  label: string; // 动作显示文本
  payload: Record<string, unknown>; // 额外载荷数据
}

// 交互式 UI 工件
export interface UIArtifact {
  surface_id: string; // Surface 标识符
  title?: string; // UI 标题
  components: UIComponent[]; // 组件列表（扁平邻接表）
  root_ids: string[]; // 根组件 ID 列表
  data: Record<string, unknown>; // 数据模型
  actions: UIAction[]; // 可触发的动作
}

// UI 数据增量更新
export interface UIDataUpdate {
  surface_id: string; // 目标 Surface 标识符
  updates: Record<string, unknown>; // 数据更新
}

// 用户动作事件（回传给 Agent）
export interface UIActionEvent {
  surface_id: string; // 来源 Surface 标识符
  action_id: string; // 触发的动作 ID
  action_type: string; // 动作类型
  data: Record<string, unknown>; // 当前 UI 的数据状态
  payload: Record<string, unknown>; // 动作携带的额外数据
}

/** 工具审批请求（Permission Engine 触发） */
export interface ToolApprovalRequest {
  requestId: string;
  toolName: string;
  toolInput: Record<string, unknown>;
  reason: string;
  timeoutSeconds: number;
  expiresAt: number;
  /** Action to take when timeout expires: "deny" (default) or "allow" */
  timeoutBehavior: 'deny' | 'allow';
  messageId: string;
  displayMode: 'approval' | 'handover';
  chatId: string;
  actionMode: ActionMode;
  batchId?: string;
  batchIndex?: number;
  batchSize?: number;
  /** URL-bearing tools: hostnames extracted from tool arguments */
  domains?: string[];
  /** Whether Domain HITL is active for this request */
  domainApproval?: boolean;
  /** PTC/MCP annotations (e.g. readOnlyHint, destructiveHint) */
  ptcAnnotations?: Record<string, boolean>;
}

/** 工具调用信息（用于 CLI Agent 权限审批和 Diff 预览） */
export interface ToolCallInfo {
  callId: string;
  toolName: string;
  arguments: Record<string, unknown>;
  requiresApproval: boolean;
  status: 'pending' | 'approved' | 'rejected' | 'completed';
  /** Diff 内容（apply_patch/edit_file 工具调用） */
  diff?: string;
  /** 文件路径 */
  filePath?: string;
  /** PTC/MCP annotations (e.g. readOnlyHint, destructiveHint) */
  ptcAnnotations?: Record<string, boolean>;
}
export type CompletionStatus = 'complete' | 'truncated' | 'filtered' | 'budget_blocked';

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
  ARTIFACT_CONTENT: 'artifact_content',
  UI_UPDATE: 'ui_update',
  TOOL_START: 'tool_start',
  TOOL_END: 'tool_end',
  TOOL_FAILURE: 'tool_failure',
  TOOL_STDOUT_CHUNK: 'tool_stdout_chunk',
  TOOL_CANCELLED: 'tool_cancelled',
  TOKEN_USAGE: 'token_usage',
  TOOL_APPROVAL_REQUEST: 'tool_approval_request',
  APPROVAL_REQUIRED: 'approval_required',
  CLARIFICATION_REQUIRED: 'clarification_required',
  APPROVAL_PROCESSED: 'approval_processed',
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
  TEAMMATE_MESSAGE: 'teammate_message',
  FILE_DIFF: 'file_diff',
  ITERATION_LIMIT_REACHED: 'iteration_limit_reached',
  CONTEXT_OVERFLOW_RESET: 'context_overflow_reset',
  STEERING: 'steering',
  TOOL_FALLBACK: 'tool_fallback',
  CONTEXT_REFERENCE_WARNING: 'context_reference_warning',
  CLIENT_ACTION: 'client_action',
  CAPTCHA_DETECTED: 'captcha_detected',
  CAPTCHA_RESOLVED: 'captcha_resolved',
  CAPTCHA_TIMEOUT: 'captcha_timeout',
  MODEL_ESCALATED: 'model_escalated',
  MODEL_FAILOVER: 'model_failover',
  MODEL_RECOVERY: 'model_recovery',
  FILE_MUTATION_FAILED: 'file_mutation_failed',
  MASCOT_XP_UPDATE: 'mascot_xp_update',
  DAG_STATE_UPDATE: 'dag_state_update',
  TOOL_IMAGE_OUTPUT: 'tool_image_output',
  BROWSER_VIEW_UPDATE: 'browser_view_update',
  DESKTOP_VIEW_UPDATE: 'desktop_view_update',
  PTC_NOTIFY: 'ptc_notify',
  TOOL_PROGRESS: 'tool_progress',
} as const;

interface BaseAgentEvent {
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

export interface ClarificationRequiredStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.CLARIFICATION_REQUIRED;
  data: ClarificationForm;
}

export interface SteeringStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.STEERING;
  data?: { count?: number; messages?: string[] } | string;
}

export interface ToolStartStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_START;
}

export interface ToolEndStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_END;
  tool_name: string;
  duration_ms: number;
  result?: unknown;
  cited_memory_ids?: string[];
  cited_memory_refs?: unknown[];
}

export interface ToolFailureStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_FAILURE;
  tool_name: string;
  duration_ms: number;
  error: string;
}

export interface ToolStdoutChunkStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_STDOUT_CHUNK;
  data: string;
}

export interface ToolCancelledStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_CANCELLED;
  tool_name: string;
  duration_ms: number;
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
  data: unknown[];
}

export type CostStatus = 'actual' | 'estimated' | 'unknown';

export type ContextHealthStatus = 'healthy' | 'warning' | 'critical';

export type ContextBudget = {
  current_tokens: number;
  max_context_tokens: number;
  usage_percent: number;
  health_status: ContextHealthStatus;
};

export interface GoalBudgetPayload {
  max_tokens?: number;
  max_usd?: number;
  max_time_seconds?: number;
  max_turns?: number;
}

export interface GoalStatusPayload {
  goal_id: string;
  objective: string;
  ui_summary?: string;
  status: import('@/components/ui/chat-window/goals/GoalStatusCard').GoalStatus;
  tokens_used: number;
  time_used_seconds: number;
  cost_usd?: number;
  turns_used?: number;
  budget?: GoalBudgetPayload;
  verdict?: string;
  reason?: string;
  should_continue?: boolean;
  constraints?: string[];
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
  type: 'goal_status';
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

export interface CatchupSnapshotStreamEvent {
  type: 'catchup_snapshot';
  messageId: string;
  data: {
    content: string;
    reasoning: string;
    progress_steps: ProgressItem[];
    sources: Source[];
  };
}

export interface ClientActionStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.CLIENT_ACTION;
  data: {
    action: string;
    payload: any;
  };
}

export interface FileDiffStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.FILE_DIFF;
  data: {
    path: string;
    diff: string;
    is_new: boolean;
    lines_added: number;
    lines_removed: number;
    truncated: boolean;
  };
}

export interface FileMutationFailedStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.FILE_MUTATION_FAILED;
  data: {
    files: FileMutationFailure[];
  };
}

export type ToolImageOutput = {
  base64: string;
  mimeType: string;
  toolName: string;
};

export interface ToolImageOutputStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_IMAGE_OUTPUT;
  tool_name: string;
  data: {
    base64: string;
    mime_type: string;
  };
}

export interface BrowserRefInfo {
  role: string;
  name: string;
  nth: number | null;
  bbox: {
    x: number;
    y: number;
    width: number;
    height: number;
    centerX: number;
    centerY: number;
    viewport_width: number;
    viewport_height: number;
  } | null;
  position: string | null;
}

export interface BrowserViewUpdateStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.BROWSER_VIEW_UPDATE;
  data: {
    screenshot_base64: string;
    mime_type: string;
    refs: Record<string, BrowserRefInfo>;
    page_url: string;
    page_title: string;
    viewport_width: number;
    viewport_height: number;
  };
}

export interface DesktopViewUpdateStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.DESKTOP_VIEW_UPDATE;
  data: {
    screenshot_base64: string;
    mime_type: string;
    refs: Record<string, BrowserRefInfo>;
    app_name: string;
    window_title: string;
    scope: string;
    needs_permission: boolean;
    viewport_width: number;
    viewport_height: number;
  };
}

export interface PtcNotifyStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.PTC_NOTIFY;
  level?: 'info' | 'warn' | 'alert';
  message?: string;
  progress?: number;
  step_index?: number;
  total_steps?: number;
  category?: string;
  session_id?: string | null;
  trace_id?: string | null;
  data?: {
    level?: 'info' | 'warn' | 'alert';
    message?: string;
    progress?: number;
    step_index?: number;
    total_steps?: number;
    category?: string;
    session_id?: string | null;
    trace_id?: string | null;
  };
}

export interface ToolProgressStreamEvent extends BaseAgentEvent {
  type: typeof AgentEventType.TOOL_PROGRESS;
  tool: string;
  progress: {
    done: number;
    total: number;
    failed: number;
  };
}

export type AgentStreamEvent =
  | ClientActionStreamEvent
  | CatchupSnapshotStreamEvent
  | PtcNotifyStreamEvent
  | ToolProgressStreamEvent
  | RateLimitUpdatedStreamEvent
  | RateLimitWarningStreamEvent
  | RateLimitThrottledStreamEvent
  | ErrorStreamEvent
  | AgentCancelledStreamEvent
  | TasksStepsStreamEvent
  | ToolHeartbeatStreamEvent
  | SourcesStreamEvent
  | ToolApprovalRequestStreamEvent
  | ApprovalProcessedStreamEvent
  | ApprovalRequiredStreamEvent
  | ClarificationRequiredStreamEvent
  | SteeringStreamEvent
  | ToolStartStreamEvent
  | ToolEndStreamEvent
  | ToolFailureStreamEvent
  | ToolStdoutChunkStreamEvent
  | ToolCancelledStreamEvent
  | TokenUsageStreamEvent
  | MessageStreamEvent
  | ArtifactsStreamEvent
  | ArtifactContentStreamEvent
  | UIUpdateStreamEvent
  | MessageEndStreamEvent
  | ReasoningStreamEvent
  | StatusStreamEvent
  | CaptchaStreamEvent
  | ModelEscalatedStreamEvent
  | ModelFailoverStreamEvent
  | ModelRecoveryStreamEvent
  | ToolsSnapshotStreamEvent
  | RoutingDecisionStreamEvent
  | PrivacyLevelStreamEvent
  | PrivacyRouteStreamEvent
  | SubagentStartStreamEvent
  | SubagentProgressStreamEvent
  | SubagentLogStreamEvent
  | SubagentCompletionStreamEvent
  | SubagentStatusUpdateStreamEvent
  | TeammateMessageStreamEvent
  | FileDiffStreamEvent
  | FileMutationFailedStreamEvent
  | ToolImageOutputStreamEvent
  | BrowserViewUpdateStreamEvent
  | DesktopViewUpdateStreamEvent
  | MascotXpUpdateStreamEvent
  | DagStateUpdateStreamEvent
  | IterationLimitReachedStreamEvent
  | ContextOverflowResetStreamEvent
  | ToolFallbackStreamEvent
  | ContextReferenceWarningStreamEvent
  | GoalStatusStreamEvent;

export type Message = {
  messageId: string;
  chatId: string;
  createdAt: Date;
  content: string;
  reasoning?: string;
  reasoningStartedAt?: number;
  reasoningDurationMs?: number;
  role: 'user' | 'assistant' | 'system';
  isCompactedSummaryView?: boolean;
  suggestions?: string[];
  sources?: Source[]; // 外部引用来源
  progressSteps?: ProgressItem[];
  searchItems?: string[];
  readingItems?: string[];
  thinkingItems?: string[];
  usage?: TokenUsage; // Token 使用量统计（最终累计）
  tokenEconomics?: TokenEconomicsSnapshot; // 细粒度成本与 Token 模型归因
  costUsd?: number; // LLM 调用总成本（USD）
  costStatus?: CostStatus; // 成本计算来源 (actual/estimated/unknown)
  cacheBreakReason?: string; // Prompt cache break 归因原因
  cacheSuggestedActions?: string; // Cache break 行动建议
  mediaAnalysisStatus?: 'analyzing_image' | 'analyzing_video' | null; // 媒体分析中的实时状态（图片/视频）
  consensusMeta?: {
    models_used: number;
    models_succeeded: number;
    aggregator_model: string;
    elapsed_seconds: number;
  };
  modelName?: string; // 最后使用的模型名称
  routingTier?: 'simple' | 'standard' | 'reasoning' | 'complex';
  privacyLevel?: SensitivityLevel;
  privacyAction?: string;
  privacyRoute?: string;
  completionStatus?: CompletionStatus; // LLM 回复完成状态
  contextBudget?: ContextBudget;
  memoryBudget?: { used: number; total: number }; // 内存注入预算
  citations?: string[]; // 引用的记忆ID
  artifacts?: Artifact[]; // 生成的工件
  uiArtifacts?: UIArtifact[]; // 交互式 UI 工件
  isFadingOut?: boolean; // 标记内容正在淡出（工具调用时清空中间内容）
  toolCalls?: ToolCallInfo[];
  files?: File[];
  sendFailed?: boolean;
  clarification?: {
    question?: string;
    answered: boolean;
    options?: string[];
    allowMultiple?: boolean;
    title?: string;
    form?: ClarificationForm;
    isResumeMode?: boolean;
  };
  metadata?: Record<string, unknown>; // 消息元数据（如错误信息、配置提示等）
  citedMemoryIds?: string[]; // 本条消息引用的记忆 ID（用于反馈评分）
  citedMemoryRefs?: CitedMemoryReference[]; // 本条消息引用的记忆详情（用于可解释 citation UI）
  fileMutationFailures?: FileMutationFailure[]; // 本轮失败的文件修改操作
  toolImages?: ToolImageOutput[]; // 工具输出的图片（如 computer_use 截屏）
  siblingGroupId?: string;
  siblingCount?: number;
  siblingIndex?: number;
};

export interface File {
  id?: string; // 文件 ID（StorageProvider 分配）
  fileName: string;
  fileExtension: string;
  fileUrl?: string; // Sandbox 模式：服务器 URL
  localPath?: string; // Tauri 模式：本地绝对路径
  fileType: 'uploaded' | 'local_path';
  contentHash?: string; // SHA-256 内容哈希，用于同会话去重
}

export interface ClarificationOption {
  id: string;
  label: string;
  description?: string;
}

export interface ClarificationQuestion {
  id: string;
  prompt: string;
  options?: ClarificationOption[];
  allowMultiple?: boolean;
}

export interface ClarificationForm {
  title?: string | null;
  questions: ClarificationQuestion[];
}

export interface ChatHistoryItem {
  id: string;
  title: string;
  firstMessage: string;
  lastMessage: string;
  actionMode: string;
  source: string;
  isCompacted?: boolean;
  isPinned?: boolean;
  pinOrder?: number;
  projectId?: string | null;
  updatedAt: Date;
  createdAt: Date;
}

export type MentionReferenceType =
  | 'workspace_file'
  | 'workspace_folder'
  | 'uploaded_file'
  | 'generated_file'
  | 'git_diff'
  | 'git_staged'
  | 'url';

export interface MentionReference {
  type: MentionReferenceType;
  label: string;
  path?: string;
  fileId?: string;
  url?: string;
  source: 'workspace' | 'uploaded' | 'generated' | 'special';
  size: number | null;
  directory?: string;
  startLine?: number;
  endLine?: number;
}

export interface ArchiveRestoreAction {
  type: 'archive_restore';
  restoreArg: string;
}

export interface ArchiveRestoreRangeHint {
  range_arg: string;
  reason?: string;
  start_line?: number;
  end_line?: number;
  label?: string;
}

export interface ArchiveRestoreContentFeature {
  feature_type: string;
  count: number;
  values: string[];
}

export interface ArchiveRestoreBlockPayload {
  type?: 'archive_restore_blocked';
  reason?: string;
  message?: string;
  suggested_action?: string;
  archive_path?: string;
  estimated_tokens?: number;
  reason_label_key?: string;
  severity?: 'info' | 'warning' | 'critical';
  primary_restore_arg?: string;
  recommended_ranges?: string[];
  restore_range_hints?: ArchiveRestoreRangeHint[];
  content_features?: ArchiveRestoreContentFeature[];
  guidance_source?: string;
  fallback_reason?: string;
}

export interface ArchiveRestoreResultPayload {
  type?: 'archive_restore_result';
  outcome?: 'restored';
  archive_path: string;
  restore_arg: string;
  start_line: number;
  end_line: number;
  restored_line_count: number;
  estimated_tokens: number;
  restored_bytes: number;
}

export interface PaginationInfo {
  page: number;
  page_size: number;
  total: number;
  total_pages: number;
  has_next: boolean;
  has_prev: boolean;
}

export interface ChatState {
  // 聊天基本信息
  chatId: string | undefined;
  newChatCreated: boolean;
  messages: Message[];
  compactedSummary: string | null;
  compactedBeforeId: string | null;
  workspaceDir: string | null;

  // 聊天历史列表（分页）
  chatHistoryItems: ChatHistoryItem[];
  chatHistoryPagination: PaginationInfo | null;
  chatHistoryLoading: boolean;
  chatHistoryError: string | null;
  chatHistorySourceFilter: string | null;
  chatHistoryAvailableSources: string[];

  // 聊天文件
  files: File[];
  cameraFrames: string[];
  hideAttachList: boolean;
  hasUsedImagesInCurrentChat: boolean;

  // @ 结构化上下文引用
  mentionReferences: MentionReference[];

  // 操作模式配置
  actionMode: ActionMode;
  searchDepth: SearchDepth;
  optimizationMode: string;
  isGoalMode: boolean;
  incognitoMode: boolean;
  goalBudgetTokens: number | null;
  goalAcceptanceCriteria: Array<Record<string, unknown>> | null;
  goalConstraints: string[] | null;

  // 智能代理模式工具开关（当前会话临时配置，切换 Agent 时从永久配置初始化）
  currentBuiltinTools: BuiltinToolId[];

  // 智能体配置
  agentConfig: AgentConfig | null;

  // 模型选择
  selectedModels: SelectedModels;
  hasUserSelectedModel: boolean;

  // 当前输入框内容（用于实时 Token 估算）
  inputMessage: string;
  pendingArchiveRestoreAction: ArchiveRestoreAction | null;
  pendingArchiveRestoreActions: ArchiveRestoreAction[];

  // 消息状态
  loading: boolean;
  loadingOlder: boolean;
  hasMoreMessages: boolean;
  nextCursor: string | null;
  messageAppeared: boolean;
  isMessagesLoaded: boolean;
  notFound: boolean;
  loadError: boolean;

  // 请求控制
  abortController: AbortController | null;

  // Regenerate sibling 状态（临时，单次请求后清除）
  regenerateSiblingGroupId?: string;
  regenerateInstruction?: string;

  // 当前会话的messageId - 用于确保文件上传和消息发送使用相同的ID
  currentSessionMessageId: string | null;

  // 智能体配置面板展开状态
  isConfigPanelExpanded: boolean;

  // 环境约束状态 — 由 SSE 事件流中的 error_category 驱动
  environmentAlerts: Set<string>;

  // 自动保存定时器 - 用于防抖
  _autoSaveTimer: NodeJS.Timeout | null;
  _messageUpdateScheduled: boolean;

  // Subagent 智能提示状态
  // Subagent 智能提示状态
  subagentPromptVisible: boolean;
  subagentPromptTimer: NodeJS.Timeout | null;
  subagentPromptMessageId: string | null;

  // 性能诊断弹窗状态
  activeSessionAnalyticsId: string | null;
  activeSessionAnalyticsMessageId: string | null;

  // 安全状态更新方法 (支持 immer)
  updateMessages: (updater: (state: ChatState) => void) => void;

  // 操作方法
  setChatId: (id: string | undefined) => void;
  setNewChatCreated: (created: boolean) => void;
  setMessages: (messages: Message[]) => void;
  setCompactedSummary: (summary: string | null) => void;
  setCompactedBeforeId: (id: string | null) => void;
  setWorkspaceDir: (dir: string | null) => void;
  setChatHistoryItems: (items: ChatHistoryItem[]) => void;
  setChatHistoryPagination: (pagination: PaginationInfo | null) => void;
  setChatHistoryLoading: (loading: boolean) => void;
  setChatHistorySourceFilter: (source: string | null) => void;
  setFiles: (files: File[]) => void;
  setCameraFrames: (frames: string[]) => void;
  setHideAttachList: (hide: boolean) => void;
  setHasUsedImagesInCurrentChat: (hasUsed: boolean) => void;
  addMentionReference: (reference: MentionReference) => void;
  removeMentionReference: (key: string) => void;
  clearMentionReferences: () => void;
  setActionMode: (mode: ActionMode) => void;
  setSearchDepth: (depth: SearchDepth) => void;
  setOptimizationMode: (mode: string) => void;
  setIsGoalMode: (isGoalMode: boolean) => void;
  setIncognitoMode: (incognitoMode: boolean) => void;
  setGoalBudgetTokens: (tokens: number | null) => void;
  setGoalAcceptanceCriteria: (criteria: Array<Record<string, unknown>> | null) => void;
  setGoalConstraints: (constraints: string[] | null) => void;
  toggleBuiltinTool: (toolId: BuiltinToolId) => void;
  setCurrentBuiltinTools: (tools: BuiltinToolId[]) => void;
  setAgentConfig: (config: AgentConfig | null) => void;
  updateAgentConfig: (partial: Partial<AgentConfig>) => void;
  setSelectedModels: (models: SelectedModels) => void;
  setInputMessage: (message: string) => void;
  setPendingArchiveRestoreAction: (action: ArchiveRestoreAction | null) => void;
  setPendingArchiveRestoreActions: (actions: ArchiveRestoreAction[]) => void;
  setLoading: (loading: boolean) => void;
  setMessageAppeared: (appeared: boolean) => void;
  setIsMessagesLoaded: (loaded: boolean) => void;
  setNotFound: (notFound: boolean) => void;
  setLoadError: (loadError: boolean) => void;
  setActiveSessionAnalyticsId: (id: string | null) => void;
  setActiveSessionAnalyticsMessageId: (id: string | null) => void;

  // 配置面板展开状态
  setConfigPanelExpanded: (expanded: boolean) => void;
  toggleConfigPanel: () => void;

  // 环境约束
  addEnvironmentAlert: (category: string) => void;
  clearEnvironmentAlerts: () => void;

  // 请求控制方法
  stopMessage: () => void;
  steerMessage: (message: string) => Promise<boolean>;

  // 当前会话messageId管理
  getCurrentSessionMessageId: () => string;
  clearCurrentSessionMessageId: () => void;
  resetSessionState: () => void;

  // Subagent 智能提示方法
  setSubagentPromptVisible: (visible: boolean) => void;
  clearSubagentPromptTimer: () => void;
  triggerSubagentPrompt: (messageId: string) => void;

  // 获取消息内容
  getMessageContent: (index: number) => string;
  // 获取聊天历史
  getChatHistory: (endIndex: number) => Message[];

  // 聊天功能
  sendMessage: (
    input: string,
    messageId?: string,
    errorMessage?: string,
    resumeValue?: unknown,
    archiveRestoreActions?: ArchiveRestoreAction[],
  ) => Promise<void>;
  // 初始化方法
  loadMessages: (chatId: string) => Promise<void>;
  loadOlderMessages: () => Promise<void>;
  initializeChat: (id?: string, initialMessage?: string | null) => void;
  scheduleAutoSave: () => void;

  // 分页聊天历史管理
  loadChatHistory: (page?: number, pageSize?: number) => Promise<void>;
  loadMoreChatHistory: () => Promise<void>;

  // Pinned Threads
  pinChat: (chatId: string) => Promise<void>;
  unpinChat: (chatId: string) => Promise<void>;
  reorderPinnedChats: (orderedIds: string[]) => Promise<void>;

  // 内部辅助方法
  _processSuggestions: (lastMsg: Message) => Promise<void>;
  // 内部辅助变量
  isReady: boolean;
}
