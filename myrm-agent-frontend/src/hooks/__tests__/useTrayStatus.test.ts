/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

let mockIsTauri = false;
let mockLoading = false;
let mockLivenessState = 'idle';
let mockBgTasks: { status: string }[] = [];

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => mockIsTauri,
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, values?: { count?: number; usage?: string }) => {
    if (key === 'trayTooltipBackground' && values?.count !== undefined) {
      return `bg:${values.count}`;
    }
    if (key === 'trayTooltipUsage' && values?.usage) {
      return `Today: ${values.usage}`;
    }
    return key;
  },
}));

const mockGetUsageStatistics = vi.fn().mockResolvedValue({ totalTokens: 0, costUsd: 0 });
const mockGetBudgetStatus = vi.fn().mockResolvedValue({ enabled: false, usage_pct: 0, remaining_usd: 0 });

vi.mock('@/services/statistics', () => ({
  getUsageStatistics: (...args: unknown[]) => mockGetUsageStatistics(...args),
}));

vi.mock('@/services/budget', () => ({
  getBudgetStatus: () => mockGetBudgetStatus(),
}));

const mockSendNotification = vi.fn();
const mockIsPermissionGranted = vi.fn().mockResolvedValue(true);
const mockRequestPermission = vi.fn().mockResolvedValue('granted');

vi.mock('@tauri-apps/plugin-notification', () => ({
  sendNotification: (...args: unknown[]) => mockSendNotification(...args),
  isPermissionGranted: () => mockIsPermissionGranted(),
  requestPermission: () => mockRequestPermission(),
}));

vi.mock('@/hooks/useLivenessState', () => ({
  useLivenessState: () => ({
    state: mockLivenessState,
    activeCount: mockLivenessState === 'busy' ? 1 : 0,
    tooltip: '',
  }),
}));

const mockListBackgroundTasks = vi.fn(async () => ({ tasks: mockBgTasks, registry_ephemeral: true }));

vi.mock('@/services/background-tasks', () => ({
  listBackgroundTasks: () => mockListBackgroundTasks(),
}));

const mockSubscribe = vi.fn((listener: () => void) => {
  listener();
  return () => undefined;
});

vi.mock('@/services/backgroundTasksRefresh', () => ({
  subscribeBackgroundTasksChanged: (listener: () => void) => mockSubscribe(listener),
}));

const mockInvoke = vi.fn();
const mockSetProgressBar = vi.fn().mockResolvedValue(undefined);
const mockRequestUserAttention = vi.fn().mockResolvedValue(undefined);

vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

vi.mock('@tauri-apps/api/window', () => ({
  getCurrentWindow: () => ({
    setProgressBar: mockSetProgressBar,
    requestUserAttention: mockRequestUserAttention,
  }),
  ProgressBarStatus: {
    None: 0,
    Normal: 1,
    Indeterminate: 2,
    Paused: 3,
    Error: 4,
  },
}));

vi.mock('@/store/useChatStore', () => {
  const store = vi.fn(() => mockLoading);
  return { default: store };
});

describe('useTrayStatus', () => {
  beforeEach(() => {
    mockIsTauri = false;
    mockLoading = false;
    mockLivenessState = 'idle';
    mockBgTasks = [];
    mockInvoke.mockReset();
    mockSetProgressBar.mockReset().mockResolvedValue(undefined);
    mockRequestUserAttention.mockReset().mockResolvedValue(undefined);
    mockListBackgroundTasks.mockClear();
    mockSubscribe.mockClear();
    mockGetUsageStatistics.mockReset().mockResolvedValue({ totalTokens: 0, costUsd: 0 });
    mockGetBudgetStatus.mockReset().mockResolvedValue({ enabled: false, usage_pct: 0, remaining_usd: 0 });
    mockSendNotification.mockClear();
    mockIsPermissionGranted.mockReset().mockResolvedValue(true);
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('does nothing in non-Tauri environment', async () => {
    mockIsTauri = false;
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
    await vi.dynamicImportSettled();
    expect(mockInvoke).not.toHaveBeenCalled();
    expect(mockSetProgressBar).not.toHaveBeenCalled();
    expect(mockListBackgroundTasks).not.toHaveBeenCalled();
  });

  it('sets idle tray + None progress when liveness is idle and no background jobs', async () => {
    mockIsTauri = true;
    mockLivenessState = 'idle';
    mockBgTasks = [];
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('set_tray_status', {
        status: 'idle',
        tooltip: 'trayTooltipIdle',
      });
    });
    expect(mockSetProgressBar).toHaveBeenCalledWith({ status: 0 });
  });

  it('sets busy tray + Indeterminate progress when liveness is busy', async () => {
    mockIsTauri = true;
    mockLivenessState = 'busy';
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('set_tray_status', {
        status: 'busy',
        tooltip: 'trayTooltipBusy',
      });
    });
    expect(mockSetProgressBar).toHaveBeenCalledWith({ status: 2 });
  });

  it('sets degraded tray when liveness is degraded', async () => {
    mockIsTauri = true;
    mockLivenessState = 'degraded';
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('set_tray_status', {
        status: 'degraded',
        tooltip: 'trayTooltipDegraded',
      });
    });
  });

  it('shows background running count in tray when liveness is idle', async () => {
    mockIsTauri = true;
    mockLivenessState = 'idle';
    mockBgTasks = [{ status: 'running' }, { status: 'running' }, { status: 'completed' }];
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('set_tray_status', {
        status: 'idle',
        tooltip: 'bg:2',
      });
    });
    expect(mockSetProgressBar).toHaveBeenCalledWith({ status: 2 });
  });

  it('requests attention on background job finish when window is hidden', async () => {
    mockIsTauri = true;
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
    await vi.dynamicImportSettled();

    Object.defineProperty(document, 'visibilityState', {
      value: 'hidden',
      writable: true,
      configurable: true,
    });

    window.dispatchEvent(
      new CustomEvent('system-notification', {
        detail: { data: { meta_data: { kind: 'background_job_finish' } } },
      }),
    );

    await waitFor(() => {
      expect(mockRequestUserAttention).toHaveBeenCalledWith(2);
    });
  });

  it('does not request attention when window is visible', async () => {
    mockIsTauri = true;
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
    await vi.dynamicImportSettled();

    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      writable: true,
      configurable: true,
    });

    window.dispatchEvent(
      new CustomEvent('system-notification', {
        detail: { data: { meta_data: { kind: 'background_job_finish' } } },
      }),
    );

    await vi.dynamicImportSettled();
    expect(mockRequestUserAttention).not.toHaveBeenCalled();
  });

  it('appends usage summary to tooltip when today has usage', async () => {
    mockIsTauri = true;
    mockLivenessState = 'idle';
    mockGetUsageStatistics.mockResolvedValue({ totalTokens: 15200, costUsd: 0.34 });
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
    await waitFor(() => {
      expect(mockInvoke).toHaveBeenCalledWith('set_tray_status', {
        status: 'idle',
        tooltip: 'trayTooltipIdle\nToday: 15.2K tokens · $0.34',
      });
    });
  });

  it('fires native notification on budget_alert event', async () => {
    mockIsTauri = true;
    mockGetBudgetStatus.mockResolvedValue({ enabled: true, usage_pct: 0.85, remaining_usd: 1.5 });
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
    await vi.dynamicImportSettled();

    window.dispatchEvent(new Event('budget_alert'));

    await waitFor(() => {
      expect(mockSendNotification).toHaveBeenCalledWith({
        title: 'budgetAlertTitle',
        body: 'budgetAlertBody',
      });
    });
  });

  it('does not fire notification when budget is disabled', async () => {
    mockIsTauri = true;
    mockGetBudgetStatus.mockResolvedValue({ enabled: false, usage_pct: 0, remaining_usd: 0 });
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
    await vi.dynamicImportSettled();

    window.dispatchEvent(new Event('budget_alert'));
    await vi.dynamicImportSettled();
    expect(mockSendNotification).not.toHaveBeenCalled();
  });

  it('silently catches errors when Tauri API fails', async () => {
    mockIsTauri = true;
    mockLoading = false;
    mockInvoke.mockRejectedValue(new Error('API unavailable'));
    const { useTrayStatus } = await import('../useTrayStatus');
    expect(() => renderHook(() => useTrayStatus())).not.toThrow();
  });
});
