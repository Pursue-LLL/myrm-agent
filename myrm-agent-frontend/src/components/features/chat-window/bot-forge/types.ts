/**
 * TypeScript types and defaults for Chat-Driven Agent & Team Factory with Builder Safety Envelope (Item 74).
 */

export type PipelineStage =
  | 'precheck'
  | 'name_overlap_guard'
  | 'profile_design'
  | 'persona_memory'
  | 'routine_bind'
  | 'post_verification'
  | 'completed'
  | 'rolled_back';

export type OverlapVerdict = 'unique' | 'duplicate_name' | 'overlapping_duty';

export type ReadinessSeverity = 'pass' | 'warning' | 'blocked';

export interface VerificationFinding {
  code: string;
  severity: ReadinessSeverity;
  message: string;
  next_action?: string;
}

export interface CreationVerificationResult {
  passed: boolean;
  severity: ReadinessSeverity;
  findings: VerificationFinding[];
  observed_state: Record<string, string>;
}

export interface RollbackRecord {
  target_name: string;
  reason: string;
  reverted_agents: string[];
  reverted_crons: string[];
  timestamp: number;
}

export interface BotProfile {
  name: string;
  display_name: string;
  description: string;
  system_prompt: string;
  model: string;
  tools: string[];
  skills: string[];
  mcp_servers: string[];
  cron_routines: string[];
  role_type: string;
}

export interface TeamComposition {
  team_name: string;
  team_purpose: string;
  lead: BotProfile;
  specialists: BotProfile[];
}

export interface PipelineExecutionState {
  pipeline_id: string;
  target_name: string;
  is_team: boolean;
  current_stage: PipelineStage;
  created_agents: string[];
  rollback?: RollbackRecord;
  verification?: CreationVerificationResult;
  error?: string;
  started_at: number;
  completed_at?: number;
}

export interface OverlapCheckResult {
  verdict: OverlapVerdict;
  conflicting_name?: string;
  recommendation?: string;
}

export const DEFAULT_CATALOG: BotProfile[] = [
  {
    name: 'research-lead',
    display_name: 'Research Lead',
    description: 'Coordinates deep literature surveys, academic paper synthesis, and citation verification',
    system_prompt: 'You lead academic research syntheses with rigorous citation verification.',
    model: 'gpt-5',
    tools: ['file_read', 'web_search'],
    skills: ['code_review', 'data_analysis'],
    mcp_servers: ['github'],
    cron_routines: ['0 9 * * 1-5'],
    role_type: 'lead',
  },
  {
    name: 'financial-analyst',
    display_name: 'Financial Analyst',
    description: 'Processes corporate balance sheets, quarterly 10-K filings, and valuation charts',
    system_prompt: 'You analyze financial statements and produce executive 3-bullet summaries.',
    model: 'claude-3-7-sonnet',
    tools: ['file_read', 'web_search'],
    skills: ['data_analysis'],
    mcp_servers: ['sqlite'],
    cron_routines: [],
    role_type: 'specialist',
  },
];

export const DEFAULT_EXECUTION_STATE: PipelineExecutionState = {
  pipeline_id: 'pipe-demo-init',
  target_name: 'research-lead',
  is_team: false,
  current_stage: 'completed',
  created_agents: ['research-lead'],
  started_at: Date.now() - 10000,
  completed_at: Date.now(),
  verification: {
    passed: true,
    severity: 'pass',
    findings: [],
    observed_state: {
      status: 'ready',
      model_ready: 'true',
      tools_bound: '2',
      skills_bound: '2',
    },
  },
};
