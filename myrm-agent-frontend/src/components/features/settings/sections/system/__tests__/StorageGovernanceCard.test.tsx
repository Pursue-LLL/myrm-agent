import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { StorageGovernanceCard } from '../StorageGovernanceCard';
import { systemService } from '@/services/system';
import { toast } from '@/hooks/shared/useToast';

const stableT = (key: string, params?: Record<string, unknown>) => {
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
      { category: 'sqlite_database', bytes: 20971520, item_count: 2, percentage: 40.0 },
      { category: 'checkpoints', bytes: 10485760, item_count: 2, percentage: 20.0 },
      { category: 'vector_store', bytes: 20971520, item_count: 85, percentage: 40.0 },
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
      expect(screen.getByText('categories.checkpoints')).toBeInTheDocument();
      expect(screen.getByText('categories.vector_store')).toBeInTheDocument();
      expect(screen.getByText('Pre-upgrade stable backup')).toBeInTheDocument();
    });
  });

  it('shows a file count for directory categories but not for the databases', async () => {
    render(<StorageGovernanceCard />);

    expect(await screen.findByText('filesCount:85')).toBeInTheDocument();
    expect(screen.queryByText('filesCount:2')).not.toBeInTheDocument();
  });

  it('tells the user in their language when a snapshot could not be created', async () => {
    (systemService.createStateSnapshot as unknown as Mock).mockResolvedValue({
      success: false,
      message: 'sqlite3.OperationalError: disk I/O error',
    });

    render(<StorageGovernanceCard />);
    fireEvent.change(await screen.findByPlaceholderText('snapshotLabelPlaceholder'), {
      target: { value: 'Manual test backup' },
    });
    fireEvent.click(screen.getByText('createSnapshot'));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({
        title: 'snapshotFailedTitle',
        description: 'snapshotFailedDesc',
        variant: 'destructive',
      });
    });
  });

  it('keeps the exception text of a failed snapshot restore out of the toast', async () => {
    (systemService.restoreStateSnapshot as unknown as Mock).mockRejectedValue(
      new Error('Request failed with status 500'),
    );

    render(<StorageGovernanceCard />);
    fireEvent.click(await screen.findByText('restore'));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({
        title: 'restoreFailedTitle',
        description: 'restoreFailedDesc',
        variant: 'destructive',
      });
    });
  });

  it('tells the user when the server refuses to delete a snapshot', async () => {
    (systemService.deleteStateSnapshot as unknown as Mock).mockResolvedValue({
      success: false,
      message: 'Snapshot not found: snap_20260901_001',
    });

    render(<StorageGovernanceCard />);
    fireEvent.click(await screen.findByRole('button', { name: 'deleteSnapshot' }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({
        title: 'deleteFailedTitle',
        description: 'deleteFailedDesc',
        variant: 'destructive',
      });
    });
  });

  it('keeps the exception text of a failed snapshot delete out of the toast', async () => {
    (systemService.deleteStateSnapshot as unknown as Mock).mockRejectedValue(
      new Error('Request failed with status 500'),
    );

    render(<StorageGovernanceCard />);
    fireEvent.click(await screen.findByRole('button', { name: 'deleteSnapshot' }));

    await waitFor(() => {
      expect(toast).toHaveBeenCalledWith({
        title: 'deleteFailedTitle',
        description: 'deleteFailedDesc',
        variant: 'destructive',
      });
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
