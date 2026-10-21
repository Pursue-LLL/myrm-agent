/**
 * TypeScript types and defaults for Heterogeneous External Agent Adapter and Subagent Bundle Manager (Item 75).
 */

export type ExternalAgentType = 'claude_code' | 'codex' | 'gemini_cli' | 'custom';

export type BundleExecutionMode = 'native_cli' | 'docker_container' | 'sandbox_isolated';

export type SubagentInstanceStatus = 'pending' | 'running' | 'completed' | 'failed' | 'terminated';

export interface ExternalBundleProfileSpec {
  bundle_id: string;
  agent_type: ExternalAgentType;
  display_name: string;
  description: string;
  binary_name: string;
  command_template: string;
  capabilities: string[];
  env_whitelist: string[];
  allowed_roots: string[];
  execution_mode: BundleExecutionMode;
  max_concurrency: number;
  is_installed: boolean;
  version: string;
}

export interface ArtifactEntry {
  type: string;
  path?: string;
  content?: string;
}

export interface SubagentInstanceRecord {
  instance_id: string;
  bundle_id: string;
  session_id: string;
  role_label: string;
  status: SubagentInstanceStatus;
  pid: number;
  task_prompt: string;
  target_workdir: string;
  created_at: number;
  started_at?: number;
  completed_at?: number;
  exit_code?: number;
  stdout_chunks: string[];
  artifacts: ArtifactEntry[];
  error?: string;
}

export interface BatchDispatchTask {
  bundle_id: string;
  role_label: string;
  task_prompt: string;
  target_subdir: string;
  timeout_seconds: number;
}

export interface BatchDispatchResult {
  batch_id: string;
  session_id: string;
  total_dispatched: number;
  dispatched_instances: SubagentInstanceRecord[];
}

export interface ProbeBundleResponse {
  bundle_id: string;
  binary_name: string;
  is_installed: boolean;
  version: string;
}

export interface TerminateInstanceResult {
  instance_id: string;
  terminated: boolean;
  status: SubagentInstanceStatus;
  error?: string;
}

export const DEFAULT_EXTERNAL_BUNDLES: ExternalBundleProfileSpec[] = [
  {
    bundle_id: 'subagent-claude-code',
    agent_type: 'claude_code',
    display_name: 'Claude Code Agent',
    description: 'Anthropic official Claude Code CLI for deep code refactoring & codebase exploration.',
    binary_name: 'claude',
    command_template: 'claude --print --prompt "{prompt}"',
    capabilities: ['code_refactor', 'terminal_execution', 'git_commit', 'lint_fix'],
    env_whitelist: ['ANTHROPIC_API_KEY', 'PATH', 'HOME'],
    allowed_roots: [],
    execution_mode: 'sandbox_isolated',
    max_concurrency: 5,
    is_installed: true,
    version: '1.2.0',
  },
  {
    bundle_id: 'subagent-codex',
    agent_type: 'codex',
    display_name: 'OpenAI Codex Specialist',
    description: 'High-speed autonomous coding subagent with granular diff generation and AST patches.',
    binary_name: 'codex',
    command_template: 'codex exec --headless --prompt "{prompt}"',
    capabilities: ['fast_patch', 'code_generation', 'unit_testing', 'syntax_repair'],
    env_whitelist: ['OPENAI_API_KEY', 'PATH'],
    allowed_roots: [],
    execution_mode: 'sandbox_isolated',
    max_concurrency: 5,
    is_installed: true,
    version: '2.4.1',
  },
  {
    bundle_id: 'subagent-gemini-cli',
    agent_type: 'gemini_cli',
    display_name: 'Gemini 2.5 Pro CLI',
    description: 'Google Gemini 2.5 long-context reasoning agent for massive codebase cross-referencing.',
    binary_name: 'gemini',
    command_template: 'gemini code --stream=false --task "{prompt}"',
    capabilities: ['deep_research', 'multi_file_analysis', 'documentation_synthesis'],
    env_whitelist: ['GEMINI_API_KEY', 'GOOGLE_API_KEY', 'PATH'],
    allowed_roots: [],
    execution_mode: 'sandbox_isolated',
    max_concurrency: 4,
    is_installed: false,
    version: '0.9.5',
  },
];

export const DEFAULT_INSTANCES: SubagentInstanceRecord[] = [
  {
    instance_id: 'inst-codex-101',
    bundle_id: 'subagent-codex',
    session_id: 'chat-demo',
    role_label: 'frontend-refactorer',
    status: 'completed',
    pid: 48912,
    task_prompt: 'Refactor chat satellite tabs to use Tailwind CSS micro-animations.',
    target_workdir: '/workspace/frontend/chat',
    created_at: Date.now() - 32000,
    started_at: Date.now() - 31500,
    completed_at: Date.now() - 4000,
    exit_code: 0,
    stdout_chunks: [
      '[codex] Analyzing AST for satellite card components...',
      '[codex] Applying transition-all duration-200 to tab switches...',
      '[artifact:diff:components/ChatSatellites.tsx] updated tabs',
    ],
    artifacts: [
      { type: 'diff', path: 'components/ChatSatellites.tsx', content: '@@ -12,4 +12,4 @@ transition-all' },
    ],
  },
  {
    instance_id: 'inst-claude-202',
    bundle_id: 'subagent-claude-code',
    session_id: 'chat-demo',
    role_label: 'security-linter',
    status: 'running',
    pid: 48925,
    task_prompt: 'Audit shell path escaping and sandbox escape vulnerabilities.',
    target_workdir: '/workspace/backend/sandbox',
    created_at: Date.now() - 15000,
    started_at: Date.now() - 14200,
    stdout_chunks: [
      '[claude] Verifying allowed_roots path containment...',
      '[claude] Scanning subprocess shlex tokenization...',
    ],
    artifacts: [],
  },
];
