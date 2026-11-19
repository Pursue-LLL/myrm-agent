/** @vitest-environment jsdom */
/**
 * [INPUT]
 * ../ResultStep (POS: 迁移向导结果步骤)
 *
 * [OUTPUT]
 * 结果页 readiness 门禁、就绪锚点、开始聊天与验证记忆入口、告警动作、会话搜索一键开启的回归测试。
 *
 * [POS]
 * 结果页以服务端复查的 readiness 为准：仍为 critical 时不能开始聊天；就绪或带警告时登记就绪锚点，
 * 并经 `/?agent_id=` 打开导入的智能体（智能体标识先转义）。会话搜索未开启时给出一键开启，已开启则不显示。
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ResultStep } from '../ResultStep';
import type { TranslationFn } from '../wizardShared';
import useChatStore from '@/store/useChatStore';

const mockPush = vi.fn();
const mockQueueMigrationReadinessAnchor = vi.fn();
const mockRecheckImportReadiness = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/lib/migrationChatHandoff', () => ({
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

/** The result step with every prop at rest; a test passes only the ones it exercises. */
const renderResultStep = (props: Partial<ComponentProps<typeof ResultStep>> = {}) =>
  render(
    <ResultStep
      result={baseResult}
      skillSubmitResult={null}
      skillSubmitFailed={false}
      secretsImport={null}
      rollingBack={false}
      onRollback={() => undefined}
      onRetrySkillSubmit={() => undefined}
      retryingSkills={false}
      onDone={() => undefined}
      t={t}
      {...props}
    />,
  );

describe('ResultStep readiness gating', () => {
  beforeEach(() => {
    mockPush.mockReset();
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

    renderResultStep({
      result: {
        ...baseResult,
        readiness: {
          status: 'critical',
          issues: [
            { code: 'providers_not_configured', severity: 'critical', params: {}, settings_path: '/settings/models' },
          ],
        },
      },
    });

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
    renderResultStep();

    await waitFor(() => {
      expect(mockQueueMigrationReadinessAnchor).toHaveBeenCalledWith({
        importBatchId: 'memory-import-batch:test',
        readinessStatus: 'ready',
        targetAgentId: 'agent-123',
      });
    });
  });

  it('starts chat when recheck reports ready', async () => {
    renderResultStep();

    const button = screen.getByRole('button', { name: 'result.startChat' });
    fireEvent.click(button);

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledExactlyOnceWith('/?agent_id=agent-123');
    });
    expect(mockQueueMigrationReadinessAnchor).toHaveBeenCalledWith({
      importBatchId: 'memory-import-batch:test',
      readinessStatus: 'ready',
      targetAgentId: 'agent-123',
    });
  });

  it('opens the imported agent by an address that is safe to put in a link', async () => {
    renderResultStep({ result: { ...baseResult, target_agent_id: 'my agent&1' } });

    fireEvent.click(screen.getByRole('button', { name: 'result.startChat' }));

    await waitFor(() => {
      expect(mockPush).toHaveBeenCalledExactlyOnceWith('/?agent_id=my%20agent%261');
    });
  });

  it('prefills a verification prompt into the composer and opens the imported agent', async () => {
    renderResultStep();

    fireEvent.click(screen.getByRole('button', { name: 'result.verifyMemory' }));

    expect(useChatStore.getState().inputMessage).toBe('result.verifyPrompt');
    expect(mockPush).toHaveBeenCalledExactlyOnceWith('/?agent_id=agent-123');
  });

  it('renders MCP issue quick-fix action', () => {
    renderResultStep({
      result: {
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
      },
    });

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
    renderResultStep();

    const button = screen.getByRole('button', { name: 'result.enableConversationSearch' });
    fireEvent.click(button);

    expect(mockConfigState.setMemoryEnableConversationSearch).toHaveBeenCalledWith(true);
    expect(mockToastSuccess).toHaveBeenCalledWith('result.conversationSearchEnabled');
  });

  it('hides enable button when conversation search is already on', () => {
    mockConfigState.memoryEnableConversationSearch = true;

    renderResultStep();

    expect(screen.queryByRole('button', { name: 'result.enableConversationSearch' })).not.toBeInTheDocument();
  });

  it('renders Codex wiki completion lane when migration source is codex', () => {
    renderResultStep({
      migrationSource: 'codex',
      workspaceBindCandidates: [
        {
          path: '/tmp/vault',
          label: 'Codex Obsidian vault',
          has_obsidian_config: true,
          markdown_file_count: 2,
        },
      ],
    });

    expect(screen.getByTestId('codex-wiki-completion-lane')).toBeTruthy();
    expect(screen.getByTestId('codex-completion-vault-hint')).toBeTruthy();
  });

  it('renders step_budget_low issue warning and action link', () => {
    renderResultStep({
      result: {
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
      },
    });

    expect(screen.getByText((content) => content.includes('result.readinessIssue.stepBudgetLow'))).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'result.readinessAction.configureStepBudget' })).toHaveAttribute(
      'href',
      '/settings?tab=agent',
    );
  });
});
