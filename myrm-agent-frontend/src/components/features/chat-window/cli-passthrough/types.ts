export type CliSubagentType =
  | 'claude_code'
  | 'codex'
  | 'cursor_cli'
  | 'generic_cli';

export type SubscriptionStatus =
  | 'active_pro'
  | 'active_team'
  | 'free_tier'
  | 'unauthenticated'
  | 'detected';

export type SensitivityLevel = 'low' | 'medium' | 'high' | 'critical';

export interface CliProfileBundleItem {
  bundleId: string;
  cliType: CliSubagentType;
  displayName: string;
  executableName: string;
  subscriptionStatus: SubscriptionStatus;
  accountEmailMasked?: string;
  defaultFlags: string[];
  timeoutSeconds: number;
  allowedWorkspaceRoot: string;
  isInstalled: boolean;
}

export interface DelegationPrivacyDisclosureItem {
  disclosureId: string;
  cliType: CliSubagentType;
  vendorName: string;
  dataHandlingTermsUrl: string;
  contextSummary: string;
  sensitivityLevel: SensitivityLevel;
  userAcknowledged: boolean;
  createdAtUtc: string;
}

export interface CliExecutionResultItem {
  taskId: string;
  bundleId: string;
  exitCode: number;
  diffOutput: string;
  structuredSummary: string;
  tokensSavedEstimate: number;
  tamperProofAuditHash: string;
  egressAccountingId: string;
  completedAtUtc: string;
  fileChangesCount: number;
}

export const DEFAULT_CLI_BUNDLES: CliProfileBundleItem[] = [
  {
    bundleId: 'bundle-claude-code',
    cliType: 'claude_code',
    displayName: 'Claude Code Subagent (Anthropic CLI)',
    executableName: 'claude',
    subscriptionStatus: 'active_pro',
    accountEmailMasked: 'u***@anthropic.com',
    defaultFlags: ['--non-interactive', '--dangerously-skip-permissions'],
    timeoutSeconds: 300,
    allowedWorkspaceRoot: '/workspace/project',
    isInstalled: true,
  },
  {
    bundleId: 'bundle-codex-cli',
    cliType: 'codex',
    displayName: 'Codex CLI Subagent (OpenAI Headless)',
    executableName: 'codex',
    subscriptionStatus: 'active_team',
    accountEmailMasked: 'd***@openai.org',
    defaultFlags: ['--quiet', '--approval-mode=auto'],
    timeoutSeconds: 240,
    allowedWorkspaceRoot: '/workspace/project',
    isInstalled: true,
  },
  {
    bundleId: 'bundle-cursor-cli',
    cliType: 'cursor_cli',
    displayName: 'Cursor Agent CLI (Headless Runner)',
    executableName: 'cursor',
    subscriptionStatus: 'active_pro',
    accountEmailMasked: 'e***@cursor.sh',
    defaultFlags: ['--headless', '--yes'],
    timeoutSeconds: 360,
    allowedWorkspaceRoot: '/workspace/project',
    isInstalled: true,
  },
];

export interface ExternalCliSubagentPassthroughCardProps {
  chatId?: string;
  initialBundles?: CliProfileBundleItem[];
  workspaceRoot?: string;
  onDismiss?: () => void;
  onExecutionCompleted?: (result: CliExecutionResultItem) => void;
  onPrivacyAcknowledged?: (disclosureId: string) => void;
}
