export type TranscriptEventKind =
  | 'thought'
  | 'tool_call'
  | 'tool_result'
  | 'state_change'
  | 'approval_requested'
  | 'approval_resolved'
  | 'denied_feedback'
  | 'summary'
  | 'error';

export type TaskDelegationStatus =
  | 'pending'
  | 'running'
  | 'paused'
  | 'waiting_approval'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type ReasoningEffortLevel = 'low' | 'medium' | 'max' | 'ultra';

export interface TranscriptEvent {
  task_id: string;
  subagent_id: string;
  seq: number;
  timestamp: number;
  kind: TranscriptEventKind;
  human_readable: string;
  payload: Record<string, string | number | boolean | null>;
}

export interface DelegationTask {
  task_id: string;
  session_id: string;
  subagent_id: string;
  role: string;
  prompt: string;
  reasoning_effort: ReasoningEffortLevel;
  status: TaskDelegationStatus;
  checkpoint_step: number;
  summary?: string;
  error_message?: string;
}

export interface SmartApproval {
  approval_id: string;
  task_id: string;
  subagent_id: string;
  command: string;
  risk_score: number;
  risk_reasons: string[];
  status: 'pending' | 'approved' | 'denied';
  deny_reason?: string;
  remediation_prompt?: string;
}

export const INITIAL_MOCK_TASK: DelegationTask = {
  task_id: 'task-hermes-019',
  session_id: 'sess-orchestration-001',
  subagent_id: 'subagent-code-auditor',
  role: 'code_auditor',
  prompt: '审计分布式账本并发安全性与高危命令执行边界',
  reasoning_effort: 'max',
  status: 'running',
  checkpoint_step: 3,
};

export const INITIAL_MOCK_EVENTS: TranscriptEvent[] = [
  {
    task_id: 'task-hermes-019',
    subagent_id: 'subagent-code-auditor',
    seq: 1,
    timestamp: Date.now() - 5000,
    kind: 'thought',
    human_readable: '初始化子任务：加载代码依赖并规划审计路径 (MoA Reasoning: MAX)',
    payload: { role: 'code_auditor', budget_tokens: 16384 },
  },
  {
    task_id: 'task-hermes-019',
    subagent_id: 'subagent-code-auditor',
    seq: 2,
    timestamp: Date.now() - 3500,
    kind: 'tool_call',
    human_readable: '调用工具 view_file 查看 core/ledger.py',
    payload: { tool: 'view_file', target: 'core/ledger.py' },
  },
  {
    task_id: 'task-hermes-019',
    subagent_id: 'subagent-code-auditor',
    seq: 3,
    timestamp: Date.now() - 2000,
    kind: 'tool_result',
    human_readable: '读取 ledger.py 成功 (142 行，CAS 锁机制就绪)',
    payload: { status: 'ok', line_count: 142 },
  },
];

export const INITIAL_MOCK_APPROVAL: SmartApproval = {
  approval_id: 'appr-hash-789a',
  task_id: 'task-hermes-019',
  subagent_id: 'subagent-code-auditor',
  command: 'rm -rf /tmp/build_cache_corrupted && git push --force',
  risk_score: 0.95,
  risk_reasons: ['Destructive recursive file removal', 'Force-pushing git history'],
  status: 'pending',
};
