/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { PreviewStep, ResultStep, type TranslationFn } from '../MigrationWizardSteps';

const mockPush = vi.fn();
const mockQueueMigrationChatAgent = vi.fn();
const mockQueueMigrationReadinessAnchor = vi.fn();
const mockRecheckImportReadiness = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/lib/migrationChatHandoff', () => ({
  queueMigrationChatAgent: (...args: unknown[]) => mockQueueMigrationChatAgent(...args),
  queueMigrationReadinessAnchor: (...args: unknown[]) => mockQueueMigrationReadinessAnchor(...args),
}));

vi.mock('@/services/memory/archive', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/memory/archive')>();
  return {
    ...actual,
    recheckImportReadiness: (...args: unknown[]) => mockRecheckImportReadiness(...args),
  };
});

const mockConfigState = vi.hoisted(() => ({
  memoryEnableConversationSearch: false,
  setMemoryEnableConversationSearch: vi.fn(),
}));

const mockToastSuccess = vi.hoisted(() => vi.fn());

const mockSonnerToast = vi.hoisted(() => {
  const fn = vi.fn();
  return Object.assign(fn, {
    success: (...args: unknown[]) => mockToastSuccess(...args),
    error: vi.fn(),
    warning: vi.fn(),
    info: vi.fn(),
    promise: vi.fn(),
    loading: vi.fn(),
    dismiss: vi.fn(),
    message: vi.fn(),
  });
});

vi.mock('@/store/useConfigStore', () => ({
  default: (selector: (state: typeof mockConfigState) => unknown) => selector(mockConfigState),
}));

vi.mock('sonner', () => ({
  toast: mockSonnerToast,
}));

const t: TranslationFn = (key, values) => (values ? `${key}:${JSON.stringify(values)}` : key);

const baseResult = {
  imported: { semantic: 2 },
  total_imported: 2,
  import_batch_id: 'memory-import-batch:test',
  payload_hash: 'hash',
  source: 'hermes',
  transaction_items: 2,
  target_agent_id: 'agent-123',
  agent_created: true,
  global_instructions_updated: false,
  workspace_rules_written: 0,
  workspace_rules_skipped: 0,
  readiness: {
    status: 'ready' as const,
    issues: [],
  },
};

describe('ResultStep readiness gating', () => {
  beforeEach(() => {
    mockPush.mockReset();
    mockQueueMigrationChatAgent.mockReset();
    mockQueueMigrationReadinessAnchor.mockReset();
    mockRecheckImportReadiness.mockReset();
    mockRecheckImportReadiness.mockResolvedValue({
      import_batch_id: 'memory-import-batch:test',
      readiness: { status: 'ready', issues: [] },
    });
  });

  it('blocks start chat after recheck still reports critical', async () => {
    mockRecheckImportReadiness.mockResolvedValue({
      import_batch_id: 'memory-import-batch:test',
      readiness: {
        status: 'critical',
        issues: [
          { code: 'providers_not_configured', severity: 'critical', params: {}, settings_path: '/settings/models' },
        ],
      },
    });

    render(
      <ResultStep
        result={{
          ...baseResult,
          readiness: {
            status: 'critical',
            issues: [
              { code: 'providers_not_configured', severity: 'critical', params: {}, settings_path: '/settings/models' },
            ],
          },
        }}
        skillSubmitResult={null}
        skillSubmitFailed={false}
        secretsImportMessage={null}
        rollingBack={false}
        onRollback={() => undefined}
        onRetrySkillSubmit={() => undefined}
        retryingSkills={false}
        onDone={() => undefined}
        t={t}
      />,
    );

    const button = screen.getByRole('button', { name: 'result.startChatRecheck' });
    expect(button).not.toBeDisabled();
    fireEvent.click(button);

    await waitFor(() => {
      expect(mockRecheckImportReadiness).toHaveBeenCalledWith('memory-import-batch:test');
    });
    expect(mockPush).not.toHaveBeenCalled();
    expect(mockQueueMigrationReadinessAnchor).not.toHaveBeenCalled();
    expect(screen.getByText('result.readinessResolveBeforeChat')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'result.readinessAction.configureProviders' })).toBeInTheDocument();
  });

  it('queues readiness anchor on mount when recheck reports ready', async () => {
    render(
      <ResultStep
        result={baseResult}
        skillSubmitResult={null}
        skillSubmitFailed={false}
        secretsImportMessage={null}
        rollingBack={false}
        onRollback={() => undefined}
        onRetrySkillSubmit={() => undefined}
        retryingSkills={false}
        onDone={() => undefined}
        t={t}
      />,
    );

    await waitFor(() => {
      expect(mockQueueMigrationReadinessAnchor).toHaveBeenCalledWith({
        importBatchId: 'memory-import-batch:test',
        readinessStatus: 'ready',
        targetAgentId: 'agent-123',
      });
    });
  });

  it('starts chat when recheck reports ready', async () => {
    render(
      <ResultStep
        result={baseResult}
        skillSubmitResult={null}
        skillSubmitFailed={false}
        secretsImportMessage={null}
        rollingBack={false}
        onRollback={() => undefined}
        onRetrySkillSubmit={() => undefined}
        retryingSkills={false}
        onDone={() => undefined}
        t={t}
      />,
    );

    const button = screen.getByRole('button', { name: 'result.startChat' });
    fireEvent.click(button);

    await waitFor(() => {
      expect(mockQueueMigrationChatAgent).toHaveBeenCalledWith('agent-123');
    });
    expect(mockQueueMigrationReadinessAnchor).toHaveBeenCalledWith({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'ready',
      targetAgentId: 'agent-123',
    });
    expect(mockPush).toHaveBeenCalledWith('/');
  });

  it('renders MCP issue quick-fix action', () => {
    render(
      <ResultStep
        result={{
          ...baseResult,
          readiness: {
            status: 'warning',
            issues: [
              {
                code: 'mcp_servers_imported_disabled',
                severity: 'warning',
                params: { count: 1 },
                settings_path: '/settings/mcp',
              },
            ],
          },
        }}
        skillSubmitResult={null}
        skillSubmitFailed={false}
        secretsImportMessage={null}
        rollingBack={false}
        onRollback={() => undefined}
        onRetrySkillSubmit={() => undefined}
        retryingSkills={false}
        onDone={() => undefined}
        t={t}
      />,
    );

    const link = screen.getByRole('link', { name: 'result.readinessAction.configureMcp' });
    expect(link).toHaveAttribute('href', '/settings/mcp');
  });
});

describe('ResultStep conversation search opt-in', () => {
  beforeEach(() => {
    mockConfigState.memoryEnableConversationSearch = false;
    mockConfigState.setMemoryEnableConversationSearch.mockReset();
    mockToastSuccess.mockReset();
  });

  it('shows enable button when conversation search is off and enables on click', () => {
    render(
      <ResultStep
        result={baseResult}
        skillSubmitResult={null}
        skillSubmitFailed={false}
        secretsImportMessage={null}
        rollingBack={false}
        onRollback={() => undefined}
        onRetrySkillSubmit={() => undefined}
        retryingSkills={false}
        onDone={() => undefined}
        t={t}
      />,
    );

    const button = screen.getByRole('button', { name: 'result.enableConversationSearch' });
    fireEvent.click(button);

    expect(mockConfigState.setMemoryEnableConversationSearch).toHaveBeenCalledWith(true);
    expect(mockToastSuccess).toHaveBeenCalledWith('result.conversationSearchEnabled');
  });

  it('hides enable button when conversation search is already on', () => {
    mockConfigState.memoryEnableConversationSearch = true;

    render(
      <ResultStep
        result={baseResult}
        skillSubmitResult={null}
        skillSubmitFailed={false}
        secretsImportMessage={null}
        rollingBack={false}
        onRollback={() => undefined}
        onRetrySkillSubmit={() => undefined}
        retryingSkills={false}
        onDone={() => undefined}
        t={t}
      />,
    );

    expect(screen.queryByRole('button', { name: 'result.enableConversationSearch' })).not.toBeInTheDocument();
  });

  it('renders Codex wiki completion lane when migration source is codex', () => {
    render(
      <ResultStep
        result={baseResult}
        skillSubmitResult={null}
        skillSubmitFailed={false}
        secretsImportMessage={null}
        rollingBack={false}
        onRollback={() => undefined}
        onRetrySkillSubmit={() => undefined}
        retryingSkills={false}
        onDone={() => undefined}
        migrationSource="codex"
        workspaceBindCandidates={[
          {
            path: '/tmp/vault',
            label: 'Codex Obsidian vault',
            has_obsidian_config: true,
            markdown_file_count: 2,
          },
        ]}
        t={t}
      />,
    );

    expect(screen.getByTestId('codex-wiki-completion-lane')).toBeTruthy();
    expect(screen.getByTestId('codex-completion-vault-hint')).toBeTruthy();
  });

  it('renders step_budget_low issue warning and action link', () => {
    render(
      <ResultStep
        result={{
          ...baseResult,
          readiness: {
            status: 'warning',
            issues: [
              {
                code: 'step_budget_low',
                severity: 'warning',
                params: { count: 1, min_steps: 100 },
                settings_path: '/settings?tab=agent',
              },
            ],
          },
        }}
        skillSubmitResult={null}
        skillSubmitFailed={false}
        secretsImportMessage={null}
        rollingBack={false}
        onRollback={() => undefined}
        onRetrySkillSubmit={() => undefined}
        retryingSkills={false}
        onDone={() => undefined}
        t={t}
      />,
    );

    expect(screen.getByText((content) => content.includes('result.readinessIssue.stepBudgetLow'))).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'result.readinessAction.configureStepBudget' })).toHaveAttribute(
      'href',
      '/settings?tab=agent',
    );
  });
});

describe('PreviewStep trusted source disclosure gate', () => {
  const dummyDryRun = {
    dry_run_id: 'dry-run-123',
    expires_at: 1800000000,
    result: {
      summary: {
        total_items: 5,
        status: 'ready' as const,
        source: 'pi',
        counts: { memory: 3, skills: 2 },
      },
      mappings: [],
      warnings: [],
      integrity_report: null,
      diagnostic_report: null,
      security_summary: null,
      recommended_action: 'proceed',
    },
    pending_skills: [
      {
        name: 'test-skill',
        description: 'a test skill',
        content_preview: 'echo hi',
      },
    ],
  };

  it('requires trusted source checkbox when importing from pi competitor', () => {
    const onConfirm = vi.fn();
    const { rerender } = render(
      <PreviewStep
        source={{
          id: 'src-1',
          name: 'Pi Agent Source',
          competitor: 'pi',
          status: 'ready',
          item_count: 5,
          skill_count: 2,
        }}
        dryRun={dummyDryRun}
        importing={false}
        importSecrets={false}
        onImportSecretsChange={vi.fn()}
        onConfirm={onConfirm}
        onBack={vi.fn()}
        t={t}
      />,
    );

    const checkbox = screen.getByTestId('migration-trusted-source-checkbox');
    expect(checkbox).not.toBeChecked();

    const confirmBtn = screen.getByRole('button', { name: 'preview.confirmImport' });
    expect(confirmBtn).toBeDisabled();

    fireEvent.click(checkbox);
    expect(checkbox).toBeChecked();
    expect(confirmBtn).not.toBeDisabled();

    fireEvent.click(confirmBtn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('does not render trusted source disclosure when source is not pi and has no skills', () => {
    const onConfirm = vi.fn();
    render(
      <PreviewStep
        source={{
          id: 'src-2',
          name: 'Hermes Source',
          competitor: 'hermes',
          status: 'ready',
          item_count: 3,
          skill_count: 0,
        }}
        dryRun={{
          ...dummyDryRun,
          pending_skills: [],
          result: {
            ...dummyDryRun.result,
            summary: {
              ...dummyDryRun.result.summary,
              source: 'hermes',
              counts: { memory: 3 },
            },
          },
        }}
        importing={false}
        importSecrets={false}
        onImportSecretsChange={vi.fn()}
        onConfirm={onConfirm}
        onBack={vi.fn()}
        t={t}
      />,
    );

    expect(screen.queryByTestId('migration-trusted-source-checkbox')).toBeNull();
    const confirmBtn = screen.getByRole('button', { name: 'preview.confirmImport' });
    expect(confirmBtn).not.toBeDisabled();
  });
});
