// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

let mockIsTauri = false;
let mockLoading = false;

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => mockIsTauri,
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
    mockInvoke.mockReset();
    mockSetProgressBar.mockReset().mockResolvedValue(undefined);
    mockRequestUserAttention.mockReset().mockResolvedValue(undefined);
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
  });

  it('sets idle tray + None progress when not generating', async () => {
    mockIsTauri = true;
    mockLoading = false;
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
    await vi.dynamicImportSettled();
    expect(mockInvoke).toHaveBeenCalledWith('set_tray_status', { status: 'idle' });
    expect(mockSetProgressBar).toHaveBeenCalledWith({ status: 0 }); // None
  });

  it('sets busy tray + Indeterminate progress when generating', async () => {
    mockIsTauri = true;
    mockLoading = true;
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
    await vi.dynamicImportSettled();
    expect(mockInvoke).toHaveBeenCalledWith('set_tray_status', { status: 'busy' });
    expect(mockSetProgressBar).toHaveBeenCalledWith({ status: 2 }); // Indeterminate
  });

  it('does not request attention when window is visible', async () => {
    mockIsTauri = true;
    mockLoading = false;
    Object.defineProperty(document, 'visibilityState', {
      value: 'visible',
      writable: true,
    });
    const { useTrayStatus } = await import('../useTrayStatus');
    renderHook(() => useTrayStatus());
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
