/**
 * [OUTPUT]
 * CostStatus, ContextHealthStatus, ContextBudget.
 *
 * [POS]
 * 成本与上下文预算指标类型。
 */

export type CostStatus = 'actual' | 'estimated' | 'unknown';

export type ContextHealthStatus = 'healthy' | 'warning' | 'critical';

export type ContextBudget = {
  current_tokens: number;
  max_context_tokens: number;
  usage_percent: number;
  health_status: ContextHealthStatus;
  messages_estimated_tokens?: number;
  bound_tools_overhead_tokens?: number;
  other_tokens?: number;
  /** 服务端 checkpoint 全量 human 消息数（与运行时 compress_processor 口径一致）。 */
  turn_count?: number;
  /** AgentLens 6-Category Fine-grained Breakdown */
  system_prompt_tokens?: number;
  memory_tokens?: number;
  workspace_rules_tokens?: number;
  mcp_tools_tokens?: number;
  skills_tools_tokens?: number;
  builtin_tools_tokens?: number;
};
