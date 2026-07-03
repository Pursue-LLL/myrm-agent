// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

let mockIsTauri = false;
let mockLoading = false;
let mockBgTasks: { status: string }[] = [];

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => mockIsTauri,
}));

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, values?: { count?: number }) => {
    if (key === 'trayTooltipBackground' && values?.count !== undefined) {
      return `bg:${values.count}`;
    }
    return key;
  },
}));

const mockListBackgroundTasks = vi.fn(async () => mockBgTasks);

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
    mockBgTasks = [];
    mockInvoke.mockReset();
    mockSetProgressBar.mockReset().mockResolvedValue(undefined);
    mockRequestUserAttention.mockReset().mockResolvedValue(undefined);
    mockListBackgroundTasks.mockClear();
    mockSubscribe.mockClear();
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

  it('sets idle tray + None progress when not generating and no background jobs', async () => {
    mockIsTauri = true;
    mockLoading = false;
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

  it('sets busy tray + Indeterminate progress when generating', async () => {
    mockIsTauri = true;
    mockLoading = true;
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

  it('shows background running count in tray when chat is idle', async () => {
    mockIsTauri = true;
    mockLoading = false;
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

  it('silently catches errors when Tauri API fails', async () => {
    mockIsTauri = true;
    mockLoading = false;
    mockInvoke.mockRejectedValue(new Error('API unavailable'));
    const { useTrayStatus } = await import('../useTrayStatus');
    expect(() => renderHook(() => useTrayStatus())).not.toThrow();
  });
});
