/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { chooseAction } from '@/lib/app-dialog';
import { confirmImportMemories, dryRunImportMemories, rollbackMemoryImport } from '@/services/memory/archive';
import { discoverMigrationSources, type ExternalSource } from '@/services/migrationDiscovery';
import MigrationWizardSection from '../MigrationWizardSection';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
const searchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({ useSearchParams: () => searchParams }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));
vi.mock('@/lib/app-dialog', () => ({ chooseAction: vi.fn() }));
vi.mock('@/lib/migrationChatHandoff', () => ({
  clearMigrationReadinessAnchor: vi.fn(),
  queueMigrationWorkspaceBindCandidates: vi.fn(),
}));
vi.mock('@/services/skill/migration', () => ({ submitSkillMigration: vi.fn() }));
vi.mock('@/services/migrationDiscovery', () => ({
  canDeepLinkMigrationSource: vi.fn(),
  discoverMigrationSources: vi.fn(),
  registerMigrationSourceManifest: vi.fn(),
  resolveMigrationImportSource: vi.fn(() => 'chatgpt'),
  importMigrationSecrets: vi.fn(),
  invalidateDiscoveryCache: vi.fn(),
  uploadMigrationZip: vi.fn(),
  PASTED_MEMORY_COMPETITOR_ID: 'pasted',
  PASTED_MEMORY_IMPORT_SOURCE: 'pasted',
}));
vi.mock('@/services/memory/archive', () => ({
  confirmImportMemories: vi.fn(),
  dryRunImportMemories: vi.fn(),
  rollbackMemoryImport: vi.fn(),
}));
const agentState = { agents: [], fetchAgents: vi.fn() };
vi.mock('@/store/useAgentStore', () => ({
  default: (select: (state: typeof agentState) => unknown) => select(agentState),
}));

// The three steps are reduced to the one control that moves the wizard forward.
const source: ExternalSource = {
  competitor: 'chatgpt',
  root: '/export',
  confidence: 'high',
  files: [],
  memory_count_estimate: 1,
  skill_count: 0,
  has_api_keys: false,
};
vi.mock('../memory-migration-wizard/ScanStep', () => ({
  ScanStep: ({ onPreview }: { onPreview: (source: ExternalSource) => void }) => (
    <button type="button" onClick={() => onPreview(source)}>
      preview
    </button>
  ),
}));
vi.mock('../memory-migration-wizard/PreviewStep', () => ({
  PreviewStep: ({ onConfirm }: { onConfirm: () => void }) => (
    <button type="button" onClick={onConfirm}>
      import
    </button>
  ),
}));
vi.mock('../memory-migration-wizard/ResultStep', () => ({
  ResultStep: ({ onRollback }: { onRollback: () => void }) => (
    <button type="button" onClick={onRollback}>
      rollback
    </button>
  ),
}));

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

/** Walks the wizard to its last step; the import did or did not create an agent. */
async function reachResultStep(agentCreated: boolean) {
  vi.mocked(confirmImportMemories).mockResolvedValue({
    import_batch_id: 'batch-1',
    agent_created: agentCreated,
  } as Awaited<ReturnType<typeof confirmImportMemories>>);
  render(<MigrationWizardSection />);
  fireEvent.click(await screen.findByRole('button', { name: 'preview' }));
  fireEvent.click(await screen.findByRole('button', { name: 'import' }));
  return screen.findByRole('button', { name: 'rollback' });
}

describe('MigrationWizardSection rollback', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(discoverMigrationSources).mockResolvedValue({
      sources: [source],
    } as Awaited<ReturnType<typeof discoverMigrationSources>>);
    vi.mocked(dryRunImportMemories).mockResolvedValue({
      dry_run_id: 'dry-1',
      pending_skills: [],
      workspace_bind_candidates: [],
    } as unknown as Awaited<ReturnType<typeof dryRunImportMemories>>);
    vi.mocked(rollbackMemoryImport).mockResolvedValue({} as Awaited<ReturnType<typeof rollbackMemoryImport>>);
  });

  it('asks what to do with the agent the import created, and deletes it when told to', async () => {
    vi.mocked(chooseAction).mockResolvedValue('delete');
    const rollback = await reachResultStep(true);

    fireEvent.click(rollback);

    await waitFor(() =>
      expect(rollbackMemoryImport).toHaveBeenCalledExactlyOnceWith('batch-1', { deleteImportedAgent: true }),
    );
    expect(chooseAction).toHaveBeenCalledExactlyOnceWith({
      variant: 'destructive',
      title: 'result.rollbackButton',
      description: 'result.rollbackDeleteAgentConfirm',
      choices: [
        { value: 'keep', label: 'result.rollbackKeepAgentAction' },
        { value: 'delete', label: 'result.rollbackDeleteAgentAction', tone: 'destructive' },
      ],
    });
  });

  it('rolls back and keeps the agent when told to keep it', async () => {
    vi.mocked(chooseAction).mockResolvedValue('keep');
    const rollback = await reachResultStep(true);

    fireEvent.click(rollback);

    await waitFor(() =>
      expect(rollbackMemoryImport).toHaveBeenCalledExactlyOnceWith('batch-1', { deleteImportedAgent: false }),
    );
  });

  it('rolls nothing back when the question is dismissed', async () => {
    vi.mocked(chooseAction).mockResolvedValue(null);
    const rollback = await reachResultStep(true);

    fireEvent.click(rollback);
    await waitFor(() => expect(chooseAction).toHaveBeenCalledTimes(1));
    await settle();

    expect(rollbackMemoryImport).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'rollback' })).toBeInTheDocument();
  });

  it('does not ask about an agent when the import created none', async () => {
    const rollback = await reachResultStep(false);

    fireEvent.click(rollback);

    await waitFor(() =>
      expect(rollbackMemoryImport).toHaveBeenCalledExactlyOnceWith('batch-1', { deleteImportedAgent: false }),
    );
    expect(chooseAction).not.toHaveBeenCalled();
  });
});
