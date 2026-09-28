/** @vitest-environment jsdom */
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import StackUpdatePanel from '../StackUpdatePanel';
import * as updatePrefs from '@/lib/update-prefs';

const mockStorage: Record<string, string> = {};
const storageMock = {
  getItem: (key: string) => mockStorage[key] ?? null,
  setItem: (key: string, val: string) => {
    mockStorage[key] = String(val);
  },
  removeItem: (key: string) => {
    delete mockStorage[key];
  },
  clear: () => {
    for (const key of Object.keys(mockStorage)) {
      delete mockStorage[key];
    }
  },
  length: 0,
  key: () => null,
};

if (typeof global.localStorage === 'undefined') {
  Object.defineProperty(global, 'localStorage', {
    value: storageMock,
    writable: true,
  });
}
if (typeof window !== 'undefined' && typeof window.localStorage === 'undefined') {
  Object.defineProperty(window, 'localStorage', {
    value: storageMock,
    writable: true,
  });
}

const mockUseAppUpdate = vi.fn();
let mockIsTauri = false;

const stableT = (key: string, params?: Record<string, unknown>) => {
  if (params) {
    return Object.entries(params).reduce((acc, [k, v]) => acc.replace(`{${k}}`, String(v)), key);
  }
  return key;
};

vi.mock('next-intl', () => ({
  useTranslations: () => stableT,
}));

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => mockIsTauri,
}));

vi.mock('@/hooks/tauri/useAppUpdate', () => ({
  useAppUpdate: (options?: unknown) => mockUseAppUpdate(options),
}));

vi.mock('@/components/features/icons/PremiumIcons', () => ({
  IconCheck: () => <span data-testid="icon-check" />,
  IconShield: () => <span data-testid="icon-shield" />,
}));

describe('StackUpdatePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsTauri = false;
    mockUseAppUpdate.mockReturnValue({
      phase: 'idle',
      info: null,
      bytesDownloaded: 0,
      totalBytes: null,
      error: null,
      check: vi.fn(),
      install: vi.fn(),
      reset: vi.fn(),
    });
    localStorage.clear();
  });

  it('renders web stack info, changelog groups, and git behind count', async () => {
    const mockPayload = {
      server_version: '0.1.0',
      harness_version: '0.1.0',
      latest: { version: 'v0.2.0', published_at: '2026-09-27T00:00:00Z' },
      stale: true,
      changelog: {
        fixed: ['Fix crash on startup', 'Repair websocket reconnect'],
        other: ['Improve UI layout', 'Speed up embeddings'],
        grouped: true,
      },
      git: { behind_count: 2, log: ['feat: stack update panel', 'fix: memory leak'] },
      prebuilt: { synced_count: 15 },
      cloud: { state: 'unknown' },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockPayload,
    } as Response);

    render(<StackUpdatePanel />);

    // Non-Tauri note
    expect(screen.getByText('desktopWebNote')).toBeInTheDocument();

    // Wait for async fetch
    await waitFor(() => {
      expect(screen.getByText(/serverRow/)).toBeInTheDocument();
    });

    expect(screen.getByText(/staleBadge/)).toBeInTheDocument();
    expect(screen.getByText(/gitBehind/)).toBeInTheDocument();
    expect(screen.getByText(/prebuiltSynced/)).toBeInTheDocument();
    expect(screen.getByText('Fix crash on startup')).toBeInTheDocument();
    expect(screen.getByText('Improve UI layout')).toBeInTheDocument();
  });

  it('toggles changelog showMore and showLess when items exceed 5', async () => {
    const mockPayload = {
      server_version: '0.1.0',
      harness_version: '0.1.0',
      latest: { version: 'v0.2.0' },
      stale: true,
      changelog: {
        fixed: ['Fix 1', 'Fix 2', 'Fix 3', 'Fix 4', 'Fix 5', 'Fix 6', 'Fix 7'],
        other: [],
        grouped: true,
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockPayload,
    } as Response);

    render(<StackUpdatePanel />);

    await waitFor(() => {
      expect(screen.getByText('Fix 1')).toBeInTheDocument();
    });

    // Default only shows first 5
    expect(screen.getByText('Fix 5')).toBeInTheDocument();
    expect(screen.queryByText('Fix 6')).not.toBeInTheDocument();

    const toggleBtn = screen.getByText('showMore');
    fireEvent.click(toggleBtn);

    // After click showMore, all 7 are visible
    expect(screen.getByText('Fix 6')).toBeInTheDocument();
    expect(screen.getByText('Fix 7')).toBeInTheDocument();
    expect(screen.getByText('showLess')).toBeInTheDocument();
  });

  it('handles defer version action and saves to updatePrefs', async () => {
    const mockPayload = {
      server_version: '0.1.0',
      harness_version: '0.1.0',
      latest: { version: 'v0.2.0' },
      stale: true,
      changelog: { fixed: [], other: [] },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockPayload,
    } as Response);

    const setDeferredSpy = vi.spyOn(updatePrefs, 'setDeferredVersion');

    render(<StackUpdatePanel />);

    await waitFor(() => {
      expect(screen.getByText(/defer/)).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText(/defer/));
    expect(setDeferredSpy).toHaveBeenCalledWith('v0.2.0');
  });

  it('executes doctor test with force=true probe and shows doctorPass on success', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        server_version: '0.1.0',
        latest: { version: 'v0.1.0' },
        fetch_error: null,
      }),
    } as Response);
    global.fetch = fetchMock;

    render(<StackUpdatePanel />);

    const doctorBtn = screen.getByText('doctorRun');
    fireEvent.click(doctorBtn);

    await waitFor(() => {
      expect(screen.getByText('doctorPass')).toBeInTheDocument();
    });
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/health/update-status?force=true');
  });

  it('disables doctor button during diagnostic probe to prevent duplicate clicks', async () => {
    let resolveProbe!: (value: unknown) => void;
    const probePromise = new Promise((resolve) => {
      resolveProbe = resolve;
    });

    global.fetch = vi.fn().mockImplementation((url: string) => {
      if (typeof url === 'string' && url.includes('force=true')) {
        return probePromise;
      }
      return Promise.resolve({
        ok: true,
        json: async () => ({}),
      });
    });

    render(<StackUpdatePanel />);

    const doctorBtn = screen.getByText('doctorRun');
    expect(doctorBtn).not.toBeDisabled();

    fireEvent.click(doctorBtn);

    expect(doctorBtn).toBeDisabled();
    expect(doctorBtn.textContent).toContain('...');

    await act(async () => {
      resolveProbe({
        ok: true,
        json: async () => ({
          server_version: '0.1.0',
          latest: { version: 'v0.1.0' },
          fetch_error: null,
        }),
      });
    });

    await waitFor(() => {
      expect(screen.getByText('doctorPass')).toBeInTheDocument();
      expect(doctorBtn).not.toBeDisabled();
    });
  });

  it('disables deferral and renders securityPatch badge when is_security is true', async () => {
    const mockPayload = {
      server_version: '0.1.0',
      harness_version: '0.1.0',
      latest: { version: 'v0.2.0' },
      stale: true,
      changelog: {
        fixed: ['CVE-2026-1234: remote code execution fix'],
        other: [],
        is_security: true,
      },
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockPayload,
    } as Response);

    render(<StackUpdatePanel />);

    await waitFor(() => {
      expect(screen.getByText('securityPatch')).toBeInTheDocument();
    });

    expect(screen.queryByText(/defer/)).not.toBeInTheDocument();
  });

  it('handles quiet hours dropdown selection', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);

    const setQuietSpy = vi.spyOn(updatePrefs, 'setQuietHours');

    render(<StackUpdatePanel />);

    await waitFor(() => {
      expect(screen.getByText('webTitle')).toBeInTheDocument();
    });

    const selects = screen.getAllByRole('combobox');
    expect(selects.length).toBe(2);

    act(() => {
      fireEvent.change(selects[0], { target: { value: '22' } });
      fireEvent.change(selects[1], { target: { value: '8' } });
    });

    expect(setQuietSpy).toHaveBeenLastCalledWith({ startHour: 22, endHour: 8 });
  });

  it('supports Tauri desktop OTA available state and install action', async () => {
    mockIsTauri = true;
    const installMock = vi.fn();

    mockUseAppUpdate.mockReturnValue({
      phase: 'available',
      info: { currentVersion: '0.1.0', version: '0.2.0', body: 'New release' },
      bytesDownloaded: 0,
      totalBytes: 1000,
      error: null,
      check: vi.fn(),
      install: installMock,
      reset: vi.fn(),
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);

    render(<StackUpdatePanel />);

    await waitFor(() => {
      expect(screen.getByText(/desktopAvailable/)).toBeInTheDocument();
    });

    const installBtn = screen.getByText('installNow');
    act(() => {
      fireEvent.click(installBtn);
    });
    expect(installMock).toHaveBeenCalled();
  });

  it('supports Tauri desktop download progress', async () => {
    mockIsTauri = true;

    mockUseAppUpdate.mockReturnValue({
      phase: 'downloading',
      info: { currentVersion: '0.1.0', version: '0.2.0', body: 'New release' },
      bytesDownloaded: 650,
      totalBytes: 1000,
      error: null,
      check: vi.fn(),
      install: vi.fn(),
      reset: vi.fn(),
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);

    render(<StackUpdatePanel />);

    await waitFor(() => {
      expect(screen.getByText(/65%/)).toBeInTheDocument();
    });
  });

  it('supports Tauri desktop up-to-date state', async () => {
    mockIsTauri = true;

    mockUseAppUpdate.mockReturnValue({
      phase: 'up_to_date',
      info: null,
      bytesDownloaded: 0,
      totalBytes: null,
      error: null,
      check: vi.fn(),
      install: vi.fn(),
      reset: vi.fn(),
    });

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({}),
    } as Response);

    render(<StackUpdatePanel />);

    await waitFor(() => {
      expect(screen.getByText('desktopUpToDate')).toBeInTheDocument();
    });
  });

  it('lists snapshots and restores with restart hint', async () => {
    mockIsTauri = false;
    mockUseAppUpdate.mockReturnValue({
      phase: 'idle',
      info: null,
      bytesDownloaded: 0,
      totalBytes: null,
      error: null,
      check: vi.fn(),
      install: vi.fn(),
      reset: vi.fn(),
    });

    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (typeof url === 'string' && url.includes('/storage/snapshots/pre-update')) {
        return { ok: true, json: async () => ({ snapshot_id: 'snap_new' }) } as Response;
      }
      if (typeof url === 'string' && url.includes('/storage/snapshots/snap_1/restore-update')) {
        expect(init?.method).toBe('POST');
        return { ok: true, json: async () => ({}) } as Response;
      }
      if (typeof url === 'string' && url.endsWith('/storage/snapshots')) {
        return {
          ok: true,
          json: async () => ({
            snapshots: [
              {
                snapshot_id: 'snap_1',
                label: 'pre-update:v0.1.0->v0.2.0',
                size_bytes: 2048,
                created_at: '2026-09-27T00:00:00Z',
                from_version: 'v0.1.0',
                to_version: 'v0.2.0',
              },
            ],
          }),
        } as Response;
      }
      return { ok: true, json: async () => ({}) } as Response;
    });
    global.fetch = fetchMock;

    render(<StackUpdatePanel />);

    await waitFor(() => {
      expect(screen.getByText('pre-update:v0.1.0->v0.2.0')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('snapshotRestore'));
    await waitFor(() => {
      expect(screen.getByText(/restoreDone/)).toBeInTheDocument();
    });
    expect(screen.getByText(/restartRequired/)).toBeInTheDocument();
  });

  it('creates a pre-update snapshot on demand', async () => {
    mockIsTauri = false;
    mockUseAppUpdate.mockReturnValue({
      phase: 'idle',
      info: null,
      bytesDownloaded: 0,
      totalBytes: null,
      error: null,
      check: vi.fn(),
      install: vi.fn(),
      reset: vi.fn(),
    });

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (typeof url === 'string' && url.includes('/storage/snapshots/pre-update')) {
        return { ok: true, json: async () => ({ snapshot_id: 'snap_new' }) } as Response;
      }
      return { ok: true, json: async () => ({ snapshots: [] }) } as Response;
    });
    global.fetch = fetchMock;

    render(<StackUpdatePanel />);

    await waitFor(() => {
      expect(screen.getByText('snapshotEmpty')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('backupNow'));
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        '/api/v1/system/storage/snapshots/pre-update',
        expect.objectContaining({ method: 'POST' }),
      );
    });
  });

  it('shows manual recovery guidance when backup fails', async () => {
    mockIsTauri = false;
    mockUseAppUpdate.mockReturnValue({
      phase: 'idle',
      info: null,
      bytesDownloaded: 0,
      totalBytes: null,
      error: null,
      check: vi.fn(),
      install: vi.fn(),
      reset: vi.fn(),
    });

    global.fetch = vi.fn(async () => {
      throw new Error('down');
    });

    render(<StackUpdatePanel />);

    await waitFor(() => {
      expect(screen.getByText('webUnknown')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('backupNow'));
    await waitFor(() => {
      expect(screen.getByText('backupFailed')).toBeInTheDocument();
    });
    expect(screen.getByText(/backupManualGuide/)).toBeInTheDocument();
  });

  it('persists the auto-backup toggle', async () => {
    mockIsTauri = false;
    mockUseAppUpdate.mockReturnValue({
      phase: 'idle',
      info: null,
      bytesDownloaded: 0,
      totalBytes: null,
      error: null,
      check: vi.fn(),
      install: vi.fn(),
      reset: vi.fn(),
    });
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ snapshots: [] }),
    } as Response);

    const setAutoSpy = vi.spyOn(updatePrefs, 'setAutoBackup');

    render(<StackUpdatePanel />);

    await waitFor(() => {
      expect(screen.getByText('backupAuto')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('backupAuto'));
    expect(setAutoSpy).toHaveBeenCalledWith(false);
  });
});
