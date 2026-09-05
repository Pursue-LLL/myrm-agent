import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, type Mock } from 'vitest';
import { StorageGovernanceCard } from '../StorageGovernanceCard';
import { systemService } from '@/services/system';

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params?.freed) return `Freed ${params.freed}`;
  if (params?.count) return `${params.count} items`;
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
        bytes: 31457280,
        item_count: 120,
        percentage: 60.0,
        details: { chats: 50, messages: 70 },
      },
      {
        category: 'vector_store',
        display_name: 'Vector Embeddings (Qdrant)',
        bytes: 20971520,
        item_count: 85,
        percentage: 40.0,
        details: { collections: 2 },
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
      expect(screen.getByText('SQLite Core Databases')).toBeInTheDocument();
      expect(screen.getByText('Vector Embeddings (Qdrant)')).toBeInTheDocument();
      expect(screen.getByText('Pre-upgrade stable backup')).toBeInTheDocument();
    });
  });

  it('triggers storage compaction and refetches report', async () => {
    (systemService.executeStorageCompaction as unknown as Mock).mockResolvedValue({
      success: true,
      initial_bytes: 52428800,
      final_bytes: 41943040,
      freed_bytes: 10485760,
      purged_checkpoints: 2,
      wal_truncated: true,
      duration_ms: 12.5,
      message: 'Compacted',
    });

    render(<StorageGovernanceCard />);

    await waitFor(() => {
      expect(screen.getByText('compactAndPurge')).toBeInTheDocument();
    });

    const compactBtn = screen.getByText('compactAndPurge');
    fireEvent.click(compactBtn);

    await waitFor(() => {
      expect(systemService.executeStorageCompaction).toHaveBeenCalled();
      expect(systemService.getStorageGovernanceReport).toHaveBeenCalledTimes(2);
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
