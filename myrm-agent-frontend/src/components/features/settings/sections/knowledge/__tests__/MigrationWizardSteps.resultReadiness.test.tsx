/** @vitest-environment jsdom */
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ResultStep, type TranslationFn } from '../MigrationWizardSteps';

const mockPush = vi.fn();
const mockQueueMigrationChatAgent = vi.fn();

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: mockPush }),
}));

vi.mock('@/lib/migrationChatHandoff', () => ({
  queueMigrationChatAgent: (...args: unknown[]) => mockQueueMigrationChatAgent(...args),
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
  });

  it('blocks start chat when readiness is critical', () => {
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

    const button = screen.getByRole('button', { name: 'result.startChatBlocked' });
    expect(button).toBeDisabled();
    expect(screen.getByText('result.readinessResolveBeforeChat')).toBeInTheDocument();
  });

  it('starts chat when readiness is ready', () => {
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
    expect(button).not.toBeDisabled();
    fireEvent.click(button);

    expect(mockQueueMigrationChatAgent).toHaveBeenCalledWith('agent-123');
    expect(mockPush).toHaveBeenCalledWith('/');
  });
});
