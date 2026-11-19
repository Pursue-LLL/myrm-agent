/** @vitest-environment jsdom */
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { toast } from 'sonner';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { dryRunImportMemories } from '@/services/memory/archive';
import {
  canDeepLinkMigrationSource,
  discoverMigrationSources,
  invalidateDiscoveryCache,
  registerMigrationSourceManifest,
  uploadMigrationZip,
  type DiscoveryResponse,
  type ExternalSource,
} from '@/services/migrationDiscovery';
import MigrationWizardSection from '../MigrationWizardSection';

const stableT = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => stableT }));
const searchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({ useSearchParams: () => searchParams }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn(), info: vi.fn() } }));
vi.mock('@/lib/app-dialog', () => ({ chooseAction: vi.fn() }));
vi.mock('@/lib/migrationChatHandoff', () => ({ clearMigrationReadinessAnchor: vi.fn() }));
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
vi.mock('@/services/memory/migratedConfigReload', () => ({ reloadMigratedConfigs: vi.fn() }));

const archive = new File(['zip'], 'export.zip');

// The steps are reduced to what the scan and the deep link drive: the sources found, a rescan, an upload, a change of
// the import settings (which re-creates the preview handler), a way back.
vi.mock('../memory-migration-wizard/ScanStep', () => ({
  ScanStep: ({
    discovery,
    onScan,
    onUpload,
    onTargetAgentIdChange,
  }: {
    discovery: DiscoveryResponse | null;
    onScan: () => void;
    onUpload: (file: File) => void;
    onTargetAgentIdChange: (value: string | null) => void;
  }) => (
    <>
      <output data-testid="sources">{discovery ? discovery.sources.map((s) => s.competitor).join(',') : 'none'}</output>
      <button type="button" onClick={onScan}>
        rescan
      </button>
      <button type="button" onClick={() => onUpload(archive)}>
        upload
      </button>
      <button type="button" onClick={() => onTargetAgentIdChange('agent-2')}>
        retarget
      </button>
    </>
  ),
}));
vi.mock('../memory-migration-wizard/PreviewStep', () => ({
  PreviewStep: ({ source, onBack }: { source: ExternalSource; onBack: () => void }) => (
    <>
      <output data-testid="previewing">{source.competitor}</output>
      <button type="button" onClick={onBack}>
        back
      </button>
    </>
  ),
}));
vi.mock('../memory-migration-wizard/ResultStep', () => ({ ResultStep: () => null }));

const source = (competitor: string): ExternalSource => ({
  competitor,
  root: `/home/user/.${competitor}`,
  confidence: 'high',
  files: [{ path: `/home/user/.${competitor}/memory.md`, kind: 'memory', size_bytes: 10 }],
  memory_count_estimate: 1,
  skill_count: 0,
  has_api_keys: false,
  can_import_secrets: false,
});

const discovered = (...competitors: string[]): DiscoveryResponse => ({
  sources: competitors.map(source),
  scan_path: '/home/user',
  available: true,
});

const settle = () =>
  act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });

describe('MigrationWizardSection discovery', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    searchParams.delete('source');
    vi.mocked(discoverMigrationSources).mockResolvedValue(discovered('hermes'));
    vi.mocked(canDeepLinkMigrationSource).mockReturnValue(true);
    vi.mocked(dryRunImportMemories).mockResolvedValue({
      dry_run_id: 'dry-1',
      pending_skills: [],
      workspace_bind_candidates: [],
    } as unknown as Awaited<ReturnType<typeof dryRunImportMemories>>);
  });

  describe('scan', () => {
    it('scans once on mount without forcing a refresh, registers the manifest it got and loads the agents', async () => {
      const manifest = [
        {
          id: 'hermes',
          display_name: 'Hermes',
          import_source: 'hermes' as const,
          discover_modes: ['local_scan' as const],
          deep_link_enabled: true,
        },
      ];
      vi.mocked(discoverMigrationSources).mockResolvedValue({
        ...discovered('hermes'),
        source_manifest: manifest,
        source_manifest_authoritative: true,
      });

      render(<MigrationWizardSection />);

      await waitFor(() => expect(screen.getByTestId('sources')).toHaveTextContent('hermes'));
      expect(discoverMigrationSources).toHaveBeenCalledExactlyOnceWith(false);
      expect(registerMigrationSourceManifest).toHaveBeenCalledExactlyOnceWith(manifest, { authoritative: true });
      expect(agentState.fetchAgents).toHaveBeenCalledExactlyOnceWith(true);
    });

    it('drops the cache and scans afresh when asked to rescan', async () => {
      render(<MigrationWizardSection />);
      await waitFor(() => expect(screen.getByTestId('sources')).toHaveTextContent('hermes'));
      vi.mocked(discoverMigrationSources).mockResolvedValue(discovered('hermes', 'openclaw'));

      fireEvent.click(screen.getByRole('button', { name: 'rescan' }));

      await waitFor(() => expect(screen.getByTestId('sources')).toHaveTextContent('hermes,openclaw'));
      expect(invalidateDiscoveryCache).toHaveBeenCalledTimes(1);
      expect(discoverMigrationSources).toHaveBeenLastCalledWith(true);
      expect(discoverMigrationSources).toHaveBeenCalledTimes(2);
    });

    it('tells the user when the scan fails', async () => {
      vi.mocked(discoverMigrationSources).mockRejectedValue(new Error('offline'));

      render(<MigrationWizardSection />);

      await waitFor(() => expect(toast.error).toHaveBeenCalledExactlyOnceWith('scanFailed'));
      expect(screen.getByTestId('sources')).toHaveTextContent('none');
    });
  });

  describe('archive upload', () => {
    it('shows what the uploaded archive holds and registers its manifest', async () => {
      const manifest = [
        {
          id: 'chatgpt',
          display_name: 'ChatGPT',
          import_source: 'chatgpt' as const,
          discover_modes: ['zip_upload' as const],
          deep_link_enabled: false,
        },
      ];
      vi.mocked(uploadMigrationZip).mockResolvedValue({
        ...discovered('chatgpt'),
        source_manifest: manifest,
        source_manifest_authoritative: false,
      });
      render(<MigrationWizardSection />);
      await waitFor(() => expect(screen.getByTestId('sources')).toHaveTextContent('hermes'));
      vi.mocked(registerMigrationSourceManifest).mockClear();

      fireEvent.click(screen.getByRole('button', { name: 'upload' }));

      await waitFor(() => expect(screen.getByTestId('sources')).toHaveTextContent('chatgpt'));
      expect(uploadMigrationZip).toHaveBeenCalledExactlyOnceWith(archive);
      expect(registerMigrationSourceManifest).toHaveBeenCalledExactlyOnceWith(manifest, { authoritative: false });
      expect(toast.info).not.toHaveBeenCalled();
    });

    it('says so when the uploaded archive holds nothing to import', async () => {
      vi.mocked(uploadMigrationZip).mockResolvedValue(discovered());
      render(<MigrationWizardSection />);
      await waitFor(() => expect(screen.getByTestId('sources')).toHaveTextContent('hermes'));

      fireEvent.click(screen.getByRole('button', { name: 'upload' }));

      await waitFor(() => expect(toast.info).toHaveBeenCalledExactlyOnceWith('cloudUploadEmpty'));
    });

    it('tells the user when the upload fails and keeps the sources it already had', async () => {
      vi.mocked(uploadMigrationZip).mockRejectedValue(new Error('too large'));
      render(<MigrationWizardSection />);
      await waitFor(() => expect(screen.getByTestId('sources')).toHaveTextContent('hermes'));

      fireEvent.click(screen.getByRole('button', { name: 'upload' }));

      await waitFor(() => expect(toast.error).toHaveBeenCalledExactlyOnceWith('cloudUploadFailed'));
      expect(screen.getByTestId('sources')).toHaveTextContent('hermes');
    });
  });

  describe('?source= deep link', () => {
    it('opens the preview of the named source once the scan has found it', async () => {
      searchParams.set('source', ' ChatGPT ');
      vi.mocked(discoverMigrationSources).mockResolvedValue(discovered('hermes', 'chatgpt'));

      render(<MigrationWizardSection />);

      expect(await screen.findByTestId('previewing')).toHaveTextContent('chatgpt');
      expect(canDeepLinkMigrationSource).toHaveBeenCalledWith('chatgpt');
      expect(dryRunImportMemories).toHaveBeenCalledExactlyOnceWith(
        {
          competitor: 'chatgpt',
          root: '/home/user/.chatgpt',
          files: ['/home/user/.chatgpt/memory.md'],
        },
        'chatgpt',
        expect.objectContaining({ apply_global_instructions: true }),
      );
    });

    it('does not open the preview again when the user comes back to the scan', async () => {
      searchParams.set('source', 'chatgpt');
      vi.mocked(discoverMigrationSources).mockResolvedValue(discovered('chatgpt'));
      render(<MigrationWizardSection />);
      fireEvent.click(await screen.findByRole('button', { name: 'back' }));
      await screen.findByRole('button', { name: 'rescan' });

      await settle();

      expect(screen.queryByTestId('previewing')).not.toBeInTheDocument();
      expect(dryRunImportMemories).toHaveBeenCalledTimes(1);
    });

    it('tries a preview that failed to start again once its settings change, and not before', async () => {
      searchParams.set('source', 'chatgpt');
      vi.mocked(discoverMigrationSources).mockResolvedValue(discovered('chatgpt'));
      vi.mocked(dryRunImportMemories).mockRejectedValueOnce(new Error('offline'));
      render(<MigrationWizardSection />);
      await waitFor(() => expect(toast.error).toHaveBeenCalledExactlyOnceWith('previewFailed'));
      await settle();
      expect(dryRunImportMemories).toHaveBeenCalledTimes(1);

      fireEvent.click(screen.getByRole('button', { name: 'retarget' }));

      expect(await screen.findByTestId('previewing')).toHaveTextContent('chatgpt');
      expect(dryRunImportMemories).toHaveBeenCalledTimes(2);
    });

    it('does nothing without the parameter', async () => {
      vi.mocked(discoverMigrationSources).mockResolvedValue(discovered('chatgpt'));

      render(<MigrationWizardSection />);
      await waitFor(() => expect(screen.getByTestId('sources')).toHaveTextContent('chatgpt'));
      await settle();

      expect(canDeepLinkMigrationSource).not.toHaveBeenCalled();
      expect(dryRunImportMemories).not.toHaveBeenCalled();
    });

    it('refuses a source the manifest does not allow to be linked', async () => {
      searchParams.set('source', 'hermes');
      vi.mocked(canDeepLinkMigrationSource).mockReturnValue(false);

      render(<MigrationWizardSection />);

      await waitFor(() => expect(toast.error).toHaveBeenCalledExactlyOnceWith('deepLinkSourceInvalid'));
      expect(dryRunImportMemories).not.toHaveBeenCalled();
    });

    it('says so when the named source was not found on this machine', async () => {
      searchParams.set('source', 'openclaw');

      render(<MigrationWizardSection />);

      await waitFor(() => expect(toast.error).toHaveBeenCalledExactlyOnceWith('deepLinkSourceNotFound'));
      expect(dryRunImportMemories).not.toHaveBeenCalled();
    });
  });
});
