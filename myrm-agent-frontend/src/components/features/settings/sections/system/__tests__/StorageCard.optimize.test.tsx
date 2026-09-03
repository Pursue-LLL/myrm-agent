import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import StorageCard from '../StorageCard';
import { systemService } from '@/services/system';
import { toast } from '@/lib/utils/toast';

const stableT = (key: string, values?: Record<string, unknown>) => {
  if (values && 'reclaimed' in values) {
    return `${key}:${values.reclaimed}:${values.percentage}`;
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => false,
  isLocalMode: () => true,
  isSandboxMode: () => false,
  getDeployMode: () => 'local',
}));

vi.mock('@/lib/utils/apiConfig', () => ({
  getBackendUrl: () => 'http://localhost:8000',
}));

vi.mock('@/lib/utils/authHeaders', () => ({
  getAuthHeaders: () => ({}),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: {
    info: vi.fn(),
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('@/services/system', () => ({
  systemService: {
    getStorageOptimizePreflight: vi.fn(),
    executeStorageOptimize: vi.fn(),
  },
}));

function makeStorageResponse() {
  return {
    ok: true,
    json: async () => ({
      data_dir: '/Users/test/.myrm',
      disk_total_bytes: 1024 * 1024 * 1024 * 20,
      disk_used_bytes: 1024 * 1024 * 1024 * 5,
      disk_free_bytes: 1024 * 1024 * 1024 * 15,
      subdirs: [
        { name: 'data.db', bytes: 1024 * 1024 * 500 }, // 500 MB
        { name: 'qdrant', bytes: 1024 * 1024 * 100 },
      ],
      db_breakdown: {
        main_db_bytes: 1024 * 1024 * 350,
        wal_bytes: 1024 * 1024 * 140,
        shm_bytes: 1024 * 1024 * 10,
        total_bytes: 1024 * 1024 * 500,
      },
    }),
  } as Response;
}

describe('StorageCard - Database Optimization Flow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(makeStorageResponse()));
  });

  it('renders database optimize button when data.db exists in storage subdirs', async () => {
    render(<StorageCard onDataDirChange={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('storageOptimizeTitle')).toBeInTheDocument();
    });
  });

  it('triggers preflight check and displays breakdown when optimize button clicked', async () => {
    vi.mocked(systemService.getStorageOptimizePreflight).mockResolvedValueOnce({
      data_dir: '/Users/test/.myrm',
      db_breakdown: {
        main_db_bytes: 1024 * 1024 * 350,
        wal_bytes: 1024 * 1024 * 140,
        shm_bytes: 1024 * 1024 * 10,
        total_bytes: 1024 * 1024 * 500,
      },
      disk_free_bytes: 1024 * 1024 * 1024 * 15,
      can_deep_optimize: true,
      recommended_mode: 'deep',
      active_background_jobs: 0,
      is_safe_to_optimize: true,
      reason: null,
    });

    render(<StorageCard onDataDirChange={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('storageOptimizeTitle')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('storageOptimizeTitle'));

    await waitFor(() => {
      expect(systemService.getStorageOptimizePreflight).toHaveBeenCalledTimes(1);
      expect(screen.getByText('storageOptimizeModeDeep')).toBeInTheDocument();
      expect(screen.getByText('storageOptimizeModeLight')).toBeInTheDocument();
    });
  });

  it('executes optimization and renders success toast & result card', async () => {
    vi.mocked(systemService.getStorageOptimizePreflight).mockResolvedValueOnce({
      data_dir: '/Users/test/.myrm',
      db_breakdown: {
        main_db_bytes: 1024 * 1024 * 350,
        wal_bytes: 1024 * 1024 * 140,
        shm_bytes: 1024 * 1024 * 10,
        total_bytes: 1024 * 1024 * 500,
      },
      disk_free_bytes: 1024 * 1024 * 1024 * 15,
      can_deep_optimize: true,
      recommended_mode: 'deep',
      active_background_jobs: 0,
      is_safe_to_optimize: true,
      reason: null,
    });

    vi.mocked(systemService.executeStorageOptimize).mockResolvedValueOnce({
      status: 'ok',
      mode: 'deep',
      before_bytes: 1024 * 1024 * 500,
      after_bytes: 1024 * 1024 * 150,
      reclaimed_bytes: 1024 * 1024 * 350,
      reclaimed_percentage: 70.0,
      backup_path: '/Users/test/.myrm/data.db.optimize_backup',
      duration_ms: 120,
      message: 'Reclaimed 367001600 bytes (70.0%) in 120ms',
    });

    render(<StorageCard onDataDirChange={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('storageOptimizeTitle')).toBeInTheDocument();
    });

    // 1. Open panel
    fireEvent.click(screen.getByText('storageOptimizeTitle'));
    await waitFor(() => {
      expect(screen.getByText('storageOptimizeModeDeep')).toBeInTheDocument();
    });

    // 2. Click execute button (it renders 'storageOptimize' text inside action area)
    const executeButtons = screen.getAllByRole('button');
    const submitBtn = executeButtons[executeButtons.length - 1];
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(systemService.executeStorageOptimize).toHaveBeenCalledWith({
        mode: 'deep',
        create_backup: true,
      });
      expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('storageOptimizeSuccess'));
      expect(screen.getByText('Reclaimed 367001600 bytes (70.0%) in 120ms')).toBeInTheDocument();
    });
  });

  it('shows warning and disables execute button when background jobs are running', async () => {
    vi.mocked(systemService.getStorageOptimizePreflight).mockResolvedValueOnce({
      data_dir: '/Users/test/.myrm',
      db_breakdown: {
        main_db_bytes: 1024 * 1024 * 350,
        wal_bytes: 1024 * 1024 * 140,
        shm_bytes: 1024 * 1024 * 10,
        total_bytes: 1024 * 1024 * 500,
      },
      disk_free_bytes: 1024 * 1024 * 1024 * 15,
      can_deep_optimize: true,
      recommended_mode: 'deep',
      active_background_jobs: 2,
      is_safe_to_optimize: false,
      reason: '2 active background job(s) running. Wait for completion before optimizing.',
    });

    render(<StorageCard onDataDirChange={vi.fn()} />);
    await waitFor(() => {
      expect(screen.getByText('storageOptimizeTitle')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('storageOptimizeTitle'));

    await waitFor(() => {
      expect(
        screen.getByText('2 active background job(s) running. Wait for completion before optimizing.'),
      ).toBeInTheDocument();
      const executeButtons = screen.getAllByRole('button');
      const submitBtn = executeButtons[executeButtons.length - 1];
      expect(submitBtn).toBeDisabled();
    });
  });
});
