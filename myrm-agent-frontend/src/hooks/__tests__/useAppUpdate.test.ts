// @vitest-environment happy-dom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

let mockIsTauri = false;

vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => mockIsTauri,
}));

const mockCheck = vi.fn();

vi.mock('@tauri-apps/plugin-updater', () => ({
  check: (...args: unknown[]) => mockCheck(...args),
}));

vi.mock('@tauri-apps/api/core', () => ({
  invoke: vi.fn(),
}));

describe('useAppUpdate (non-Tauri)', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mockIsTauri = false;
    mockCheck.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('should return idle phase in non-Tauri environment', async () => {
    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate());

    expect(result.current.phase).toBe('idle');
    expect(result.current.info).toBeNull();
    expect(result.current.error).toBeNull();
    expect(result.current.bytesDownloaded).toBe(0);
    expect(result.current.totalBytes).toBeNull();
  });

  it('should expose check, install, reset functions', async () => {
    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate());

    expect(typeof result.current.check).toBe('function');
    expect(typeof result.current.install).toBe('function');
    expect(typeof result.current.reset).toBe('function');
  });

  it('check() should be a no-op in non-Tauri environment', async () => {
    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate());

    await act(async () => {
      await result.current.check();
    });

    expect(result.current.phase).toBe('idle');
  });

  it('install() should be a no-op when no pending update', async () => {
    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate());

    await act(async () => {
      await result.current.install();
    });

    expect(result.current.phase).toBe('idle');
  });

  it('reset() should remain idle when already idle', async () => {
    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate());

    act(() => {
      result.current.reset();
    });

    expect(result.current.phase).toBe('idle');
    expect(result.current.error).toBeNull();
    expect(result.current.bytesDownloaded).toBe(0);
    expect(result.current.totalBytes).toBeNull();
  });

  it('should export useAppUpdate function', async () => {
    const mod = await import('../useAppUpdate');
    expect(mod.useAppUpdate).toBeDefined();
  });
});

describe('useAppUpdate (Tauri mock)', () => {
  const mockDownload = vi.fn();
  const mockInstall = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    mockIsTauri = true;
    mockCheck.mockReset();
    mockDownload.mockReset();
    mockInstall.mockReset();
  });

  afterEach(() => {
    vi.useRealTimers();
    mockIsTauri = false;
  });

  it('should transition to up_to_date when no update available', async () => {
    mockCheck.mockResolvedValue(null);

    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate({ autoCheck: false }));

    expect(result.current.phase).toBe('idle');

    await act(async () => {
      await result.current.check();
    });

    expect(result.current.phase).toBe('up_to_date');
    expect(result.current.info).toBeNull();
  });

  it('should transition to available when update found', async () => {
    const mockUpdate = {
      currentVersion: '0.1.0',
      version: '0.2.0',
      body: 'Bug fixes and improvements',
      download: mockDownload,
      install: mockInstall,
    };
    mockCheck.mockResolvedValue(mockUpdate);

    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate({ autoCheck: false, autoDownload: false }));

    await act(async () => {
      await result.current.check();
    });

    expect(result.current.phase).toBe('available');
    expect(result.current.info).toEqual({
      currentVersion: '0.1.0',
      version: '0.2.0',
      body: 'Bug fixes and improvements',
    });
  });

  it('should handle check error gracefully', async () => {
    mockCheck.mockRejectedValue(new Error('Network error'));

    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate({ autoCheck: false }));

    await act(async () => {
      await result.current.check();
    });

    expect(result.current.phase).toBe('error');
    expect(result.current.error).toBe('Network error');
  });

  it('should auto-check after initial delay', async () => {
    mockCheck.mockResolvedValue(null);

    const { useAppUpdate } = await import('../useAppUpdate');
    renderHook(() => useAppUpdate({ autoCheck: true, initialCheckDelayMs: 2000, recheckIntervalMs: 0 }));

    expect(mockCheck).not.toHaveBeenCalled();

    await act(async () => {
      vi.advanceTimersByTime(2100);
    });

    expect(mockCheck).toHaveBeenCalledTimes(1);
  });

  it('should auto-download when phase becomes available', async () => {
    mockDownload.mockImplementation((cb: (event: Record<string, unknown>) => void) => {
      cb({ event: 'Started', data: { contentLength: 5000 } });
      cb({ event: 'Progress', data: { chunkLength: 2500 } });
      cb({ event: 'Progress', data: { chunkLength: 2500 } });
      return Promise.resolve();
    });

    const mockUpdate = {
      currentVersion: '0.1.0',
      version: '0.3.0',
      body: 'New features',
      download: mockDownload,
      install: mockInstall,
    };
    mockCheck.mockResolvedValue(mockUpdate);

    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate({ autoCheck: false, autoDownload: true }));

    await act(async () => {
      await result.current.check();
    });
    expect(result.current.phase).toBe('available');

    await act(async () => {
      vi.advanceTimersByTime(1100);
    });

    expect(mockDownload).toHaveBeenCalled();
    expect(result.current.phase).toBe('ready');
    expect(result.current.bytesDownloaded).toBe(5000);
    expect(result.current.totalBytes).toBe(5000);
  });

  it('should handle download error gracefully', async () => {
    mockDownload.mockRejectedValue(new Error('Download failed'));

    const mockUpdate = {
      currentVersion: '0.1.0',
      version: '0.4.0',
      body: '',
      download: mockDownload,
      install: mockInstall,
    };
    mockCheck.mockResolvedValue(mockUpdate);

    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate({ autoCheck: false, autoDownload: true }));

    await act(async () => {
      await result.current.check();
    });

    await act(async () => {
      vi.advanceTimersByTime(1100);
    });

    expect(result.current.phase).toBe('error');
    expect(result.current.error).toBe('Download failed');
  });

  it('should reset from error back to idle', async () => {
    mockCheck.mockRejectedValue(new Error('Test error'));

    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate({ autoCheck: false }));

    await act(async () => {
      await result.current.check();
    });
    expect(result.current.phase).toBe('error');

    act(() => {
      result.current.reset();
    });

    expect(result.current.phase).toBe('idle');
    expect(result.current.error).toBeNull();
  });

  it('should not check when already downloading', async () => {
    let downloadResolve: () => void;
    mockDownload.mockImplementation(
      () =>
        new Promise<void>((resolve) => {
          downloadResolve = resolve;
        }),
    );

    const mockUpdate = {
      currentVersion: '0.1.0',
      version: '0.5.0',
      body: '',
      download: mockDownload,
      install: mockInstall,
    };
    mockCheck.mockResolvedValue(mockUpdate);

    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate({ autoCheck: false, autoDownload: true }));

    await act(async () => {
      await result.current.check();
    });

    await act(async () => {
      vi.advanceTimersByTime(1100);
    });
    expect(result.current.phase).toBe('downloading');

    mockCheck.mockClear();
    await act(async () => {
      await result.current.check();
    });
    expect(mockCheck).not.toHaveBeenCalled();

    await act(async () => {
      downloadResolve!();
    });
  });

  it('should install and invoke restart_app', async () => {
    mockDownload.mockResolvedValue(undefined);
    mockInstall.mockResolvedValue(undefined);

    const mockUpdate = {
      currentVersion: '0.1.0',
      version: '0.7.0',
      body: 'Install test',
      download: mockDownload,
      install: mockInstall,
    };
    mockCheck.mockResolvedValue(mockUpdate);

    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate({ autoCheck: false, autoDownload: false }));

    await act(async () => {
      await result.current.check();
    });
    expect(result.current.phase).toBe('available');

    await act(async () => {
      await result.current.install();
    });

    expect(mockInstall).toHaveBeenCalled();
    expect(result.current.phase).toBe('restarting');
  });

  it('should handle install error', async () => {
    mockDownload.mockResolvedValue(undefined);
    mockInstall.mockRejectedValue(new Error('Install failed'));

    const mockUpdate = {
      currentVersion: '0.1.0',
      version: '0.8.0',
      body: '',
      download: mockDownload,
      install: mockInstall,
    };
    mockCheck.mockResolvedValue(mockUpdate);

    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate({ autoCheck: false, autoDownload: false }));

    await act(async () => {
      await result.current.check();
    });

    await act(async () => {
      await result.current.install();
    });

    expect(result.current.phase).toBe('error');
    expect(result.current.error).toBe('Install failed');
  });

  it('should recheck on interval', async () => {
    mockCheck.mockResolvedValue(null);

    const { useAppUpdate } = await import('../useAppUpdate');
    renderHook(() => useAppUpdate({ autoCheck: true, initialCheckDelayMs: 100, recheckIntervalMs: 5000 }));

    await act(async () => {
      vi.advanceTimersByTime(200);
    });
    expect(mockCheck).toHaveBeenCalledTimes(1);

    await act(async () => {
      vi.advanceTimersByTime(5100);
    });
    expect(mockCheck).toHaveBeenCalledTimes(2);
  });

  it('should handle null body in update info', async () => {
    const mockUpdate = {
      currentVersion: '0.1.0',
      version: '0.6.0',
      body: null as unknown as string,
      download: mockDownload,
      install: mockInstall,
    };
    mockCheck.mockResolvedValue(mockUpdate);

    const { useAppUpdate } = await import('../useAppUpdate');
    const { result } = renderHook(() => useAppUpdate({ autoCheck: false, autoDownload: false }));

    await act(async () => {
      await result.current.check();
    });

    expect(result.current.phase).toBe('available');
    expect(result.current.info?.body).toBe('');
  });
});
