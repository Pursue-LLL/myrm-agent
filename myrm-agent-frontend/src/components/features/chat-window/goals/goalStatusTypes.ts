export type GoalStatus =
  | 'queued'
  | 'active'
  | 'pending_approval'
  | 'paused'
  | 'wait'
  | 'budget_limited'
  | 'complete'
  | 'cancelled'
  | 'needs_human_review';

export interface AcceptanceResultItem {
  label: string;
  passed: boolean;
  duration_ms: number;
  reason?: string;
  error_logs?: string;
}

export interface AcceptanceHistoryEntry {
  timestamp: string;
  results: AcceptanceResultItem[];
}

export interface GoalState {
  goalId: string;
  objective: string;
  uiSummary?: string;
  status: GoalStatus;
  tokensUsed: number;
  timeUsedSeconds: number;
  costUsd?: number;
  turnsUsed?: number;
  budget?: {
    maxTokens?: number;
    maxUsd?: number;
    maxTimeSeconds?: number;
    maxTurns?: number;
    convergenceWindow?: number;
    loopOnPause?: boolean;
    maxLoopRestarts?: number;
  };
  noProgressStreak?: number;
  loopRestarts?: number;
  verdict?: string;
  reason?: string;
  constraints?: string[];
  acceptanceCriteria?: { type: string; command?: string; criteria?: string }[];
  acceptanceResults?: AcceptanceResultItem[];
  acceptanceHistory?: AcceptanceHistoryEntry[];
  checkpointMode?: 'none' | 'per_todo';
  subgoals?: { text: string }[];
  deliverables?: { id: string; filename: string }[];
  executionSummary?: {
    files_modified: string[];
    verifications: { cmd: string; passed: boolean }[];
    browser_checks: number;
    total_tokens: number;
    total_cost_usd: number;
    execution_duration_s: number;
    turns_used: number;
  };
}
