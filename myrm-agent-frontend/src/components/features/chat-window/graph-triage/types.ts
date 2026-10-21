export type TriageVerdictType =
  | 'admit_graph'
  | 'reject_to_single_agent'
  | 'reject_to_conversational'
  | 'reject_to_linear_pipeline';

export type TaskComplexityCategoryType =
  | 'simple_single_step'
  | 'exploratory_chat'
  | 'strictly_sequential'
  | 'parallel_heavyweight';

export type BudgetStatusType = 'healthy' | 'warning' | 'critical' | 'exhausted';

export interface TriageFeatures {
  prompt_length: number;
  declared_subtasks_count: number;
  independent_parallel_count: number;
  max_dependency_depth: number;
  is_conversational_inquiry: boolean;
  has_isolated_heavyweight_steps: boolean;
}

export interface TriageDecision {
  verdict: TriageVerdictType;
  category: TaskComplexityCategoryType;
  reason: string;
  recommended_mode: string;
  estimated_speedup_ratio: number;
  estimated_tokens_saved: number;
  features: TriageFeatures;
}

export interface BudgetEstimate {
  total_estimated_tokens: number;
  estimated_cost_usd: number;
  max_tokens_cap: number;
  max_cost_usd_cap: number;
  is_circuit_broken: boolean;
  recommendation: string;
}

export interface ExecutionSpendState {
  session_id: string;
  current_tokens: number;
  current_cost_usd: number;
  remaining_tokens: number;
  remaining_budget_pct: number;
  budget_status: BudgetStatusType;
  active_concurrency: number;
  is_throttled: boolean;
  is_circuit_broken: boolean;
}

export interface NodeExecutionOutput {
  node_id: string;
  status: 'completed' | 'running' | 'pending';
  result_summary: string;
  tokens_used: number;
}

export interface PartialReduceReport {
  session_id: string;
  summary: string;
  completed_nodes: string[];
  unexecuted_nodes: string[];
  tokens_spent: number;
  tokens_saved: number;
  delivery_confidence: number;
  reason: string;
}

export const INITIAL_MOCK_DECISION: TriageDecision = {
  verdict: 'admit_graph',
  category: 'parallel_heavyweight',
  reason: '检测到 3 个独立可并行的重型模块安全审计子任务，准许激活多智能体图并发编排。',
  recommended_mode: 'Parallel Multi-Agent Graph Engine',
  estimated_speedup_ratio: 3.2,
  estimated_tokens_saved: 0,
  features: {
    prompt_length: 128,
    declared_subtasks_count: 4,
    independent_parallel_count: 3,
    max_dependency_depth: 2,
    is_conversational_inquiry: false,
    has_isolated_heavyweight_steps: true,
  },
};

export const INITIAL_MOCK_ESTIMATE: BudgetEstimate = {
  total_estimated_tokens: 47500,
  estimated_cost_usd: 0.1425,
  max_tokens_cap: 100000,
  max_cost_usd_cap: 2.0,
  is_circuit_broken: false,
  recommendation: 'ALLOW: 预估资源消耗在安全硬上限阈值内。',
};

export const INITIAL_MOCK_SPEND: ExecutionSpendState = {
  session_id: 'graph-triage-demo-session',
  current_tokens: 15000,
  current_cost_usd: 0.045,
  remaining_tokens: 85000,
  remaining_budget_pct: 0.85,
  budget_status: 'healthy',
  active_concurrency: 4,
  is_throttled: false,
  is_circuit_broken: false,
};
