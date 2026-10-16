import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { StorageGovernanceCard } from '../StorageGovernanceCard';
import { systemService } from '@/services/system';
import { toast } from '@/hooks/shared/useToast';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.freed) {
    return `Freed ${params.freed}`;
  }
  if (params?.count !== undefined) {
    return `${key}:${params.count}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/hooks/shared/useToast', () => ({
  toast: vi.fn(),
}));

vi.mock('@/services/system', () => ({
  systemService: {
    getStorageGovernanceReport: vi.fn(),
    executeStorageCompaction: vi.fn(),
    createStateSnapshot: vi.fn(),
    restoreStateSnapshot: vi.fn(),
    deleteStateSnapshot: vi.fn(),
  },
}));

describe('StorageGovernanceCard', () => {
  const mockReport = {
    total_storage_bytes: 52428800, // 50MB
    disk_total_bytes: 107374182400, // 100GB
    disk_free_bytes: 85899345920, // 80GB
    disk_used_percentage: 20.0,
    categories: [
      {
        category: 'sqlite_database',
        display_name: 'SQLite Core Databases',
        bytes: 20971520,
        item_count: 2,
        percentage: 40.0,
        details: { chats: 50, messages: 70 },
      },
      {
        category: 'checkpoints',
        display_name: 'Conversation Checkpoints',
        bytes: 10485760,
        item_count: 2,
        percentage: 20.0,
        details: {},
      },
      {
        category: 'vector_store',
        display_name: 'Vector Embeddings (Qdrant)',
        bytes: 20971520,
        item_count: 85,
        percentage: 40.0,
        details: { collections: 2 },
      },
      {
        category: 'future_subsystem',
        display_name: 'Future Subsystem',
        bytes: 1024,
        item_count: 1,
        percentage: 0.1,
        details: {},
      },
    ],
    snapshots: [
      {
        snapshot_id: 'snap_20260901_001',
        label: 'Pre-upgrade stable backup',
        size_bytes: 31457280,
        created_at: '2026-09-01T12:00:00Z',
        checksum: 'sha256:abcd1234',
        file_count: 3,
      },
    ],
    recommended_actions: [],
    is_growth_healthy: true,
    generated_at: '2026-09-01T12:05:00Z',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    (systemService.getStorageGovernanceReport as unknown as Mock).mockResolvedValue(mockReport);
  });

  it('renders storage volume metrics and category breakdown', async () => {
    render(<StorageGovernanceCard />);

    await waitFor(() => {
      expect(screen.getByText('50.00 MB')).toBeInTheDocument();
      expect(screen.getByText('categories.sqlite_database')).toBeInTheDocument();
      expect(screen.getByText('categories.vector_store')).toBeInTheDocument();
      // A category the card has no label for keeps the name the backend reports.
      expect(screen.getByText('Future Subsystem')).toBeInTheDocument();
      expect(screen.queryByText('SQLite Core Databases')).not.toBeInTheDocument();
      expect(screen.getByText('Pre-upgrade stable backup')).toBeInTheDocument();
    });
  });

  it('shows a file count for directory categories but not for the databases', async () => {
    render(<StorageGovernanceCard />);

    expect(await screen.findByText('filesCount:85')).toBeInTheDocument();
    expect(screen.queryByText('filesCount:2')).not.toBeInTheDocument();
  });

  it('triggers storage compaction and refetches report', async () => {
    (systemService.executeStorageCompaction as unknown as Mock).mockResolvedValue({
      success: true,
      initial_bytes: 52428800,
      final_bytes: 41943040,
      freed_bytes: 10485760,
      wal_truncated: true,
      duration_ms: 12.5,
      message: 'Compacted',
    });

    render(<StorageGovernanceCard />);

    await waitFor(() => {
      expect(screen.getByText('compactDatabase')).toBeInTheDocument();
    });

    const compactBtn = screen.getByText('compactDatabase');
    fireEvent.click(compactBtn);

    await waitFor(() => {
      expect(systemService.executeStorageCompaction).toHaveBeenCalled();
      expect(systemService.getStorageGovernanceReport).toHaveBeenCalledTimes(2);
    });
  });

  it('tells the user in their language when compaction did not complete', async () => {
    (systemService.executeStorageCompaction as unknown as Mock).mockResolvedValue({
      success: false,
      initial_bytes: 52428800,
      final_bytes: 52428800,
      freed_bytes: 0,
      wal_truncated: false,
      duration_ms: 3.1,
      message: 'State database compaction did not complete.',
    });

    render(<StorageGovernanceCard />);
    fireEvent.click(await screen.findByText('compactDatabase'));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'compactionFailedTitle',
          description: 'compactionFailedDesc',
          variant: 'destructive',
        }),
      );
    });
    expect(systemService.getStorageGovernanceReport).toHaveBeenCalledTimes(1);
  });

  it('keeps the technical error of a failed compaction request out of the toast', async () => {
    (systemService.executeStorageCompaction as unknown as Mock).mockRejectedValue(
      new Error('sqlite3.OperationalError: database is locked'),
    );

    render(<StorageGovernanceCard />);
    fireEvent.click(await screen.findByText('compactDatabase'));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'compactionFailedTitle',
          description: 'compactionFailedDesc',
          variant: 'destructive',
        }),
      );
    });
  });

  it('creates and restores state snapshot', async () => {
    (systemService.createStateSnapshot as unknown as Mock).mockResolvedValue({
      success: true,
      message: 'Snapshot created',
    });
    (systemService.restoreStateSnapshot as unknown as Mock).mockResolvedValue({
      success: true,
      message: 'Restored',
    });

    render(<StorageGovernanceCard />);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('snapshotLabelPlaceholder')).toBeInTheDocument();
    });

    const input = screen.getByPlaceholderText('snapshotLabelPlaceholder');
    fireEvent.change(input, { target: { value: 'Manual test backup' } });

    const createBtn = screen.getByText('createSnapshot');
    fireEvent.click(createBtn);

    await waitFor(() => {
      expect(systemService.createStateSnapshot).toHaveBeenCalledWith('Manual test backup');
    });

    const restoreBtn = screen.getByText('restore');
    fireEvent.click(restoreBtn);

    await waitFor(() => {
      expect(systemService.restoreStateSnapshot).toHaveBeenCalledWith('snap_20260901_001');
    });
  });
});
