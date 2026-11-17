/** @vitest-environment jsdom */
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { confirmImportMemories, dryRunImportMemories } from '@/services/memory/archive';
import {
  discoverMigrationSources,
  importMigrationSecrets,
  type ExternalSource,
  type SecretsImportResponse,
} from '@/services/migrationDiscovery';
import MigrationWizardSection from '../MigrationWizardSection';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
vi.mock('next/navigation', () => ({ useSearchParams: () => new URLSearchParams() }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));
vi.mock('@/lib/app-dialog', () => ({ chooseAction: vi.fn() }));
vi.mock('@/lib/migrationChatHandoff', () => ({ clearMigrationReadinessAnchor: vi.fn() }));
vi.mock('@/services/skill/migration', () => ({ submitSkillMigration: vi.fn() }));
vi.mock('@/services/migrationDiscovery', () => ({
  canDeepLinkMigrationSource: vi.fn(),
  discoverMigrationSources: vi.fn(),
  registerMigrationSourceManifest: vi.fn(),
  resolveMigrationImportSource: vi.fn(() => 'hermes'),
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

// The steps are reduced to the controls that drive the key import and the one that shows what it reported.
let scanned: ExternalSource;
vi.mock('../memory-migration-wizard/ScanStep', () => ({
  ScanStep: ({ onPreview }: { onPreview: (source: ExternalSource) => void }) => (
    <button type="button" onClick={() => onPreview(scanned)}>
      preview
    </button>
  ),
}));
vi.mock('../memory-migration-wizard/PreviewStep', () => ({
  PreviewStep: ({
    onConfirm,
    onImportSecretsChange,
  }: {
    onConfirm: () => void;
    onImportSecretsChange: (value: boolean) => void;
  }) => (
    <>
      <button type="button" onClick={() => onImportSecretsChange(true)}>
        tick
      </button>
      <button type="button" onClick={onConfirm}>
        import
      </button>
    </>
  ),
}));
vi.mock('../memory-migration-wizard/ResultStep', () => ({
  ResultStep: ({ secretsImport }: { secretsImport: SecretsImportResponse | null }) => (
    <output data-testid="secrets-import">{JSON.stringify(secretsImport)}</output>
  ),
}));

const hermes = (overrides: Partial<ExternalSource> = {}): ExternalSource => ({
  competitor: 'hermes',
  root: '/home/user/.hermes',
  confidence: 'high',
  files: [],
  memory_count_estimate: 1,
  skill_count: 0,
  has_api_keys: true,
  can_import_secrets: true,
  ...overrides,
});

/** Walks the wizard through the import; resolves with what the result step received. */
async function runImport({ source, ticked }: { source: ExternalSource; ticked: boolean }) {
  scanned = source;
  render(<MigrationWizardSection />);
  fireEvent.click(await screen.findByRole('button', { name: 'preview' }));
  if (ticked) {
    fireEvent.click(await screen.findByRole('button', { name: 'tick' }));
  }
  fireEvent.click(await screen.findByRole('button', { name: 'import' }));
  return screen.findByTestId('secrets-import');
}

describe('MigrationWizardSection key import', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(discoverMigrationSources).mockResolvedValue({
      sources: [hermes()],
    } as Awaited<ReturnType<typeof discoverMigrationSources>>);
    vi.mocked(dryRunImportMemories).mockResolvedValue({
      dry_run_id: 'dry-1',
      pending_skills: [],
      workspace_bind_candidates: [],
    } as unknown as Awaited<ReturnType<typeof dryRunImportMemories>>);
    vi.mocked(confirmImportMemories).mockResolvedValue({
      import_batch_id: 'batch-1',
      agent_created: false,
    } as Awaited<ReturnType<typeof confirmImportMemories>>);
  });

  it('imports the keys when asked and hands the structured result to the result step', async () => {
    const reported: SecretsImportResponse = {
      imported_keys: ['OPENAI_API_KEY'],
      skipped_keys: [{ name: 'MINIMAX_API_KEY', reason: 'needs_endpoint' }],
    };
    vi.mocked(importMigrationSecrets).mockResolvedValue(reported);

    const result = await runImport({ source: hermes(), ticked: true });

    expect(importMigrationSecrets).toHaveBeenCalledExactlyOnceWith('hermes', '/home/user/.hermes');
    await waitFor(() => expect(JSON.parse(result.textContent ?? '')).toEqual(reported));
    expect(toast.success).toHaveBeenCalledExactlyOnceWith('secretsImportSuccess');
  });

  it('warns that nothing was imported when every key needs manual setup', async () => {
    vi.mocked(importMigrationSecrets).mockResolvedValue({
      imported_keys: [],
      skipped_keys: [{ name: 'KIMI_API_KEY', reason: 'needs_endpoint' }],
    });

    await runImport({ source: hermes(), ticked: true });

    expect(toast.warning).toHaveBeenCalledExactlyOnceWith('secretsImportPartialSkip');
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('keeps the memory import and tells the user to enter the keys by hand when the key import fails', async () => {
    vi.mocked(importMigrationSecrets).mockRejectedValue(new Error('Providers config is not an object'));

    const result = await runImport({ source: hermes(), ticked: true });

    expect(toast.warning).toHaveBeenCalledExactlyOnceWith('secretsImportFailed');
    expect(result.textContent).toBe('null');
  });

  it('never touches provider settings when the box was left unticked', async () => {
    await runImport({ source: hermes(), ticked: false });

    expect(importMigrationSecrets).not.toHaveBeenCalled();
  });

  it('never touches provider settings for a source whose keys the import cannot bring', async () => {
    await runImport({ source: hermes({ has_api_keys: true, can_import_secrets: false }), ticked: true });

    expect(importMigrationSecrets).not.toHaveBeenCalled();
  });
});
