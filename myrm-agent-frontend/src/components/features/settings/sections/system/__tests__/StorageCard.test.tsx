import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import StorageCard from '../StorageCard';
import { toast } from '@/lib/utils/toast';
import { invoke } from '@tauri-apps/api/core';
import { open } from '@tauri-apps/plugin-dialog';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => true,
}));

vi.mock('@/lib/utils/apiConfig', () => ({
  getBackendUrl: () => 'http://localhost:8000',
}));

vi.mock('@/lib/utils/authHeaders', () => ({
  getAuthHeaders: () => ({}),
}));

vi.mock('@/lib/utils/classnameUtils', () => ({
  cn: (...args: string[]) => args.filter(Boolean).join(' '),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@tauri-apps/plugin-dialog', () => ({
  open: vi.fn(() => Promise.resolve('/tmp/new-data-dir')),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(() => Promise.resolve(undefined)),
}));

function makeStorageResponse() {
  return {
    ok: true,
    json: async () => ({
      data_dir: '/Users/test/.myrm',
      disk_total_bytes: 1024 * 1024 * 1024 * 10,
      disk_used_bytes: 1024 * 1024 * 1024 * 2,
      disk_free_bytes: 1024 * 1024 * 1024 * 8,
      subdirs: [],
    }),
  } as Response;
}

describe('StorageCard security-sensitive migration flow', () => {
  const onDataDirChange = vi.fn();
  const invokeMock = vi.mocked(invoke);
  const openDialogMock = vi.mocked(open);
  const toastInfoMock = vi.mocked(toast.info);
  const toastSuccessMock = vi.mocked(toast.success);
  const toastErrorMock = vi.mocked(toast.error);
  const fetchMock = vi.fn<(...args: unknown[]) => Promise<Response>>();

  beforeEach(() => {
    onDataDirChange.mockReset();
    invokeMock.mockReset();
    openDialogMock.mockReset();
    toastInfoMock.mockReset();
    toastSuccessMock.mockReset();
    toastErrorMock.mockReset();
    fetchMock.mockReset();

    fetchMock.mockResolvedValue(makeStorageResponse());
    vi.stubGlobal('fetch', fetchMock);
    openDialogMock.mockResolvedValue('/tmp/new-data-dir');
    invokeMock.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('issues ticket before migrate_data_dir and applies directory change', async () => {
    invokeMock.mockResolvedValueOnce('ticket-migrate-1').mockResolvedValueOnce(undefined);

    render(<StorageCard onDataDirChange={onDataDirChange} />);
    await waitFor(() => {
      expect(screen.getByText('storageChange')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('storageChange'));

    await waitFor(() => {
      expect(invokeMock).toHaveBeenNthCalledWith(1, 'issue_sensitive_action_ticket', {
        action: 'migrate_data_dir',
      });
      expect(invokeMock).toHaveBeenNthCalledWith(2, 'migrate_data_dir', {
        newDir: '/tmp/new-data-dir',
        actionTicket: 'ticket-migrate-1',
      });
    });

    expect(onDataDirChange).toHaveBeenCalledWith('/tmp/new-data-dir');
    expect(toastInfoMock).toHaveBeenCalledWith('storageMigrating');
    expect(toastSuccessMock).toHaveBeenCalledWith('storageMigrateSuccess');
  });

  it('does not issue ticket when directory selection is canceled', async () => {
    openDialogMock.mockResolvedValueOnce(null);

    render(<StorageCard onDataDirChange={onDataDirChange} />);
    await waitFor(() => {
      expect(screen.getByText('storageChange')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('storageChange'));

    await waitFor(() => {
      expect(invokeMock).not.toHaveBeenCalled();
    });

    expect(onDataDirChange).not.toHaveBeenCalled();
  });

  it('reports cancellation-style backend failure to user', async () => {
    invokeMock
      .mockResolvedValueOnce('ticket-migrate-2')
      .mockRejectedValueOnce(new Error('Sensitive action cancelled by user'));

    render(<StorageCard onDataDirChange={onDataDirChange} />);
    await waitFor(() => {
      expect(screen.getByText('storageChange')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('storageChange'));

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith(
        expect.stringContaining('Sensitive action cancelled by user'),
      );
    });

    expect(onDataDirChange).not.toHaveBeenCalled();
  });
});
