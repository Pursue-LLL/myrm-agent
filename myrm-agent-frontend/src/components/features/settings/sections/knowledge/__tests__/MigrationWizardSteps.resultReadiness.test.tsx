/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ResultStep, type TranslationFn } from '../MigrationWizardSteps';

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

vi.mock('@/services/memoryArchive', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/memoryArchive')>();
  return {
    ...actual,
    recheckImportReadiness: (...args: unknown[]) => mockRecheckImportReadiness(...args),
  };
});

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
        issues: [{ code: 'providers_not_configured', severity: 'critical', params: {} }],
      },
    });

    render(
      <ResultStep
        result={{
          ...baseResult,
          readiness: {
            status: 'critical',
            issues: [{ code: 'providers_not_configured', severity: 'critical', params: {} }],
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
            issues: [{ code: 'mcp_servers_imported_disabled', severity: 'warning', params: { count: 1 } }],
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
