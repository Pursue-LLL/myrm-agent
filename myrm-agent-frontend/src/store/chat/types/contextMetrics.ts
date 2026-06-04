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
};
