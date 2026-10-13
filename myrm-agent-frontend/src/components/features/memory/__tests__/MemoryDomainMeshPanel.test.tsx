/** @vitest-environment jsdom */
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest';
import { MemoryDomainMeshPanel } from '../mesh/MemoryDomainMeshPanel';
import * as domainMeshService from '@/services/memory/domainMesh';
import { toast } from '@/hooks/shared/useToast';
import en from '../../../../../locales/en.json';
import zh from '../../../../../locales/zh.json';

// The global setup stubs next-intl with an identity translator; this suite asserts the real locale copy.
vi.mock('next-intl', async (importOriginal) => importOriginal<typeof import('next-intl')>());

vi.mock('@/services/memory/domainMesh', () => ({
  getDomainMeshOverview: vi.fn(),
  getMemoryDrillDown: vi.fn(),
  migrateFromHermes: vi.fn(),
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: vi.fn(),
}));

const LOCALE_MESSAGES = { en, zh } as const;

const renderPanel = (locale: keyof typeof LOCALE_MESSAGES = 'en') => {
  const { mesh, types } = LOCALE_MESSAGES[locale].memory;
  return render(
    <NextIntlClientProvider locale={locale} messages={{ memory: { mesh, types } }}>
      <MemoryDomainMeshPanel />
    </NextIntlClientProvider>,
  );
};

const preferenceDrillDown: domainMeshService.DrillDownResponse = {
  id: 'user-1',
  domain: 'user',
  category: 'preferences',
  memory_type: 'semantic',
  l0: 'Dark mode user preference',
  l1: 'User prefers dark theme with high contrast',
  l2_content: 'Full verbatim text of the dark mode preference item.',
  created_at: '2026-09-18T00:00:00Z',
  updated_at: '2026-09-18T00:00:00Z',
  metadata: {},
};

const mockOverview: domainMeshService.DomainMeshOverviewResponse = {
  total_memories: 3,
  user: {
    domain: 'user',
    total_count: 1,
    category_counts: { preferences: 1 },
    highlights: [
      {
        id: 'user-1',
        l0: 'Dark mode user preference',
        l1: 'User prefers dark theme with high contrast',
        category: 'preferences',
        memory_type: 'semantic',
        updated_at: '2026-09-18T00:00:00Z',
      },
    ],
  },
  assistant: {
    domain: 'assistant',
    total_count: 1,
    category_counts: { soul: 1 },
    highlights: [
      {
        id: 'asst-1',
        l0: 'Calm assistant persona',
        l1: 'Assistant always responds politely and concisely',
        category: 'soul',
        memory_type: 'semantic',
        updated_at: '2026-09-18T00:00:00Z',
      },
    ],
  },
  task: {
    domain: 'task',
    total_count: 1,
    category_counts: { traps: 1 },
    highlights: [
      {
        id: 'task-1',
        l0: 'Avoid destructive git reset',
        l1: 'Never use git reset without uncommitted work review',
        category: 'traps',
        memory_type: 'procedural',
        updated_at: '2026-09-18T00:00:00Z',
      },
    ],
  },
};

describe('MemoryDomainMeshPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(domainMeshService.getDomainMeshOverview).mockResolvedValue(mockOverview);
  });

  it('renders three domain cards and their highlights', async () => {
    renderPanel();

    expect(screen.getByText('Three-Domain Memory Mesh')).toBeInTheDocument();
    expect(screen.getByText('Multi-Domain Sync')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('User Domain')).toBeInTheDocument();
      expect(screen.getByText('Assistant Domain')).toBeInTheDocument();
      expect(screen.getByText('Task Domain')).toBeInTheDocument();
    });

    expect(screen.getByText('Dark mode user preference')).toBeInTheDocument();
    expect(screen.getByText('Calm assistant persona')).toBeInTheDocument();
    expect(screen.getByText('Avoid destructive git reset')).toBeInTheDocument();
  });

  it('renders the copy of the active locale', async () => {
    renderPanel('zh');

    expect(screen.getByText(zh.memory.mesh.panel.title)).toBeInTheDocument();
    expect(screen.getByText(zh.memory.mesh.panel.badge)).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText(zh.memory.mesh.domains.user.title)).toBeInTheDocument();
      expect(screen.getByText(zh.memory.mesh.domains.assistant.title)).toBeInTheDocument();
      expect(screen.getByText(zh.memory.mesh.domains.task.title)).toBeInTheDocument();
    });
    expect(screen.getAllByText(zh.memory.mesh.card.highlights)).toHaveLength(3);
    expect(screen.queryByText('Three-Domain Memory Mesh')).not.toBeInTheDocument();
  });

  it('falls back to a localized label for untitled and empty domains', async () => {
    vi.mocked(domainMeshService.getDomainMeshOverview).mockResolvedValue({
      ...mockOverview,
      user: { ...mockOverview.user, highlights: [{ ...mockOverview.user.highlights[0], l0: '' }] },
      assistant: { ...mockOverview.assistant, total_count: 0, highlights: [] },
      task: { ...mockOverview.task, total_count: 0, highlights: [] },
    });

    renderPanel();

    expect(await screen.findByText('Untitled Memory')).toBeInTheDocument();
    expect(screen.getAllByText('No memories indexed in this domain yet.')).toHaveLength(2);
  });

  it('shows a localized notice instead of the raw error when the overview fails to load, and retries', async () => {
    vi.mocked(domainMeshService.getDomainMeshOverview).mockRejectedValueOnce(new Error('HTTP 500: upstream exploded'));

    renderPanel();

    expect(await screen.findByText('Failed to load domain mesh overview')).toBeInTheDocument();
    expect(screen.queryByText(/upstream exploded/)).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }));

    await waitFor(() => {
      expect(screen.queryByText('Failed to load domain mesh overview')).not.toBeInTheDocument();
    });
    expect(domainMeshService.getDomainMeshOverview).toHaveBeenCalledTimes(2);
    expect(await screen.findByText('Dark mode user preference')).toBeInTheDocument();
  });

  it('opens drill-down dialog when a highlight card is clicked', async () => {
    vi.mocked(domainMeshService.getMemoryDrillDown).mockResolvedValue(preferenceDrillDown);

    renderPanel();

    await waitFor(() => {
      expect(screen.getByText('Dark mode user preference')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Dark mode user preference'));

    await waitFor(() => {
      expect(screen.getByText('Memory Details & Traceability')).toBeInTheDocument();
      expect(screen.getByText('Full verbatim text of the dark mode preference item.')).toBeInTheDocument();
    });
  });

  describe('identifiers returned by the API', () => {
    it('are shown by their names in the active locale on the cards and in the drill-down', async () => {
      vi.mocked(domainMeshService.getMemoryDrillDown).mockResolvedValue(preferenceDrillDown);
      const { mesh, types } = zh.memory;

      renderPanel('zh');

      expect(await screen.findAllByText(mesh.categories.preferences)).toHaveLength(2);
      expect(screen.getAllByText(mesh.categories.soul)).toHaveLength(2);
      expect(screen.getAllByText(mesh.categories.traps)).toHaveLength(2);
      expect(screen.queryByText('preferences')).not.toBeInTheDocument();

      fireEvent.click(screen.getByText('Dark mode user preference'));

      expect(
        await screen.findByText(`${mesh.domains.user.title} / ${mesh.categories.preferences}`),
      ).toBeInTheDocument();
      expect(screen.getByText(types.semantic)).toBeInTheDocument();
      expect(screen.getByText(new Date(preferenceDrillDown.updated_at).toLocaleString('zh'))).toBeInTheDocument();
    });

    it('are shown as-is when this build has no name for them', async () => {
      vi.mocked(domainMeshService.getDomainMeshOverview).mockResolvedValue({
        ...mockOverview,
        user: { ...mockOverview.user, category_counts: { recipes: 2 } },
      });

      renderPanel();

      expect(await screen.findByText('recipes')).toBeInTheDocument();
    });
  });

  describe('copying the full content', () => {
    const openDrillDown = async (writeText: (text: string) => Promise<void>) => {
      Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true });
      vi.mocked(domainMeshService.getMemoryDrillDown).mockResolvedValue(preferenceDrillDown);
      renderPanel();
      fireEvent.click(await screen.findByText('Dark mode user preference'));
      return screen.findByRole('button', { name: 'Copy' });
    };

    afterEach(() => {
      Reflect.deleteProperty(navigator, 'clipboard');
    });

    it('confirms the copy once the clipboard accepted the text', async () => {
      const writeText = vi.fn().mockResolvedValue(undefined);

      fireEvent.click(await openDrillDown(writeText));

      expect(await screen.findByText('Copied')).toBeInTheDocument();
      expect(writeText).toHaveBeenCalledWith(preferenceDrillDown.l2_content);
    });

    it('does not claim success when the clipboard refuses the text', async () => {
      const writeText = vi.fn().mockRejectedValue(new Error('denied'));

      fireEvent.click(await openDrillDown(writeText));

      await waitFor(() => expect(writeText).toHaveBeenCalled());
      expect(screen.queryByText('Copied')).not.toBeInTheDocument();
      expect(screen.getByRole('button', { name: 'Copy' })).toBeInTheDocument();
    });
  });

  it('shows a not-found state without exposing the memory id when the drill-down cannot be loaded', async () => {
    vi.mocked(domainMeshService.getMemoryDrillDown).mockRejectedValue(new Error('404'));

    renderPanel();

    fireEvent.click(await screen.findByText('Dark mode user preference'));

    expect(await screen.findByText('Memory Not Found')).toBeInTheDocument();
    expect(screen.getByText('Unable to load details for this memory.')).toBeInTheDocument();
    expect(screen.queryByText(/user-1/)).not.toBeInTheDocument();
  });

  it('opens migration modal when Migrate from Hermes is clicked', async () => {
    renderPanel();

    await waitFor(() => {
      expect(screen.getByText('User Domain')).toBeInTheDocument();
    });

    const migrateBtn = screen.getByText('Migrate from Hermes');
    fireEvent.click(migrateBtn);

    await waitFor(() => {
      expect(screen.getByText('Import from Hermes or OpenViking')).toBeInTheDocument();
      expect(screen.getByText('Start Lossless Import')).toBeInTheDocument();
    });
  });

  describe('Hermes migration', () => {
    const openMigrationWith = async (content: string) => {
      renderPanel();
      fireEvent.click(await screen.findByText('Migrate from Hermes'));
      fireEvent.change(await screen.findByRole('textbox'), { target: { value: content } });
    };

    it('keeps the import action disabled until there is content to import', async () => {
      renderPanel();
      fireEvent.click(await screen.findByText('Migrate from Hermes'));

      const start = (await screen.findByText('Start Lossless Import')).closest('button');
      expect(start).toBeDisabled();

      fireEvent.change(screen.getByRole('textbox'), { target: { value: '# note' } });
      expect(start).toBeEnabled();
    });

    it('reports the imported and failed counts and refreshes the overview after a successful import', async () => {
      vi.mocked(domainMeshService.migrateFromHermes).mockResolvedValue({
        success_count: 2,
        fail_count: 1,
        message: 'done',
      });

      await openMigrationWith('# note');
      fireEvent.click(screen.getByText('Start Lossless Import'));

      await waitFor(() => {
        expect(toast).toHaveBeenCalledWith({
          title: 'Migration Completed',
          description: 'Successfully imported 2 memories (1 failed).',
        });
      });
      expect(domainMeshService.migrateFromHermes).toHaveBeenCalledWith({ content: '# note', format: 'markdown' });
      await waitFor(() => {
        expect(domainMeshService.getDomainMeshOverview).toHaveBeenCalledTimes(2);
      });
    });

    it('keeps the dialog and the pasted text when nothing could be imported', async () => {
      vi.mocked(domainMeshService.migrateFromHermes).mockResolvedValue({
        success_count: 0,
        fail_count: 1,
        message: 'Migration completed: 0 imported, 1 failed.',
      });

      await openMigrationWith('not an export');
      fireEvent.click(screen.getByText('Start Lossless Import'));

      await waitFor(() => {
        expect(toast).toHaveBeenCalledWith({
          title: 'Migration Failed',
          description: en.memory.mesh.migration.nothingImported,
          variant: 'destructive',
        });
      });
      expect(screen.getByRole('textbox')).toHaveValue('not an export');
      expect(screen.getByText('Import from Hermes or OpenViking')).toBeInTheDocument();
      expect(domainMeshService.getDomainMeshOverview).toHaveBeenCalledTimes(1);
    });

    it('never surfaces the raw failure message when the import fails', async () => {
      vi.mocked(domainMeshService.migrateFromHermes).mockRejectedValue(new Error('HTTP 500: upstream exploded'));

      await openMigrationWith('# note');
      fireEvent.click(screen.getByText('Start Lossless Import'));

      await waitFor(() => {
        expect(toast).toHaveBeenCalledWith({
          title: 'Migration Failed',
          description: 'An error occurred during migration.',
          variant: 'destructive',
        });
      });
    });
  });

  it('handles extremely long verbatim content in drill-down dialog safely with scroll container', async () => {
    const longContent = 'A'.repeat(5000);
    vi.mocked(domainMeshService.getMemoryDrillDown).mockResolvedValue({
      id: 'task-1',
      domain: 'task',
      category: 'traps',
      memory_type: 'procedural',
      l0: 'Avoid destructive git reset',
      l1: 'Never use git reset without uncommitted work review',
      l2_content: longContent,
      created_at: '2026-09-18T00:00:00Z',
      updated_at: '2026-09-18T00:00:00Z',
      metadata: {},
    });

    renderPanel();

    await waitFor(() => {
      expect(screen.getByText('Avoid destructive git reset')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Avoid destructive git reset'));

    await waitFor(() => {
      expect(screen.getByText('Memory Details & Traceability')).toBeInTheDocument();
      expect(screen.getByText(longContent)).toBeInTheDocument();
      const preEl = screen.getByText(longContent);
      expect(preEl.className).toContain('overflow-y-auto');
      expect(preEl.className).toContain('max-h-[48vh]');
    });
  });
});
