import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook } from '@testing-library/react';

let mockIsTauriRuntime = false;
vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => mockIsTauriRuntime,
  isLocalMode: () => true,
  getDeployMode: () => 'tauri',
}));

type ListenCallback<T> = (event: { payload: T }) => void;
const mockListeners = new Map<string, ListenCallback<unknown>>();
const mockUnlisten = vi.fn();

vi.mock('@tauri-apps/api/event', () => ({
  listen: vi.fn(async (eventName: string, callback: ListenCallback<unknown>) => {
    mockListeners.set(eventName, callback);
    return mockUnlisten;
  }),
}));

import { useVoicePttListener } from '../useVoicePttListener';

describe('useVoicePttListener', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListeners.clear();
    mockIsTauriRuntime = false;
  });

  afterEach(() => {
    mockIsTauriRuntime = false;
  });

  it('does nothing in non-Tauri environment', () => {
    mockIsTauriRuntime = false;
    renderHook(() => useVoicePttListener());
    expect(mockListeners.size).toBe(0);
  });

  it('registers all three PTT listeners in Tauri', async () => {
    mockIsTauriRuntime = true;
    renderHook(() => useVoicePttListener());

    await vi.waitFor(() => {
      expect(mockListeners.has('voice-ptt-start')).toBe(true);
      expect(mockListeners.has('voice-ptt-stop')).toBe(true);
      expect(mockListeners.has('voice-ptt-context')).toBe(true);
    });
  });

  it('dispatches cancelable DOM CustomEvent on voice-ptt-start', async () => {
    mockIsTauriRuntime = true;
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    renderHook(() => useVoicePttListener());

    await vi.waitFor(() => expect(mockListeners.has('voice-ptt-start')).toBe(true));

    mockListeners.get('voice-ptt-start')!({ payload: undefined });

    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'voice-ptt-start',
        cancelable: true,
      }),
    );
    dispatchSpy.mockRestore();
  });

  it('dispatches cancelable DOM CustomEvent on voice-ptt-stop', async () => {
    mockIsTauriRuntime = true;
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    renderHook(() => useVoicePttListener());

    await vi.waitFor(() => expect(mockListeners.has('voice-ptt-stop')).toBe(true));

    mockListeners.get('voice-ptt-stop')!({ payload: undefined });

    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'voice-ptt-stop',
        cancelable: true,
      }),
    );
    dispatchSpy.mockRestore();
  });

  it('dispatches DOM CustomEvent with PttScreenContext on voice-ptt-context', async () => {
    mockIsTauriRuntime = true;
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    renderHook(() => useVoicePttListener());

    await vi.waitFor(() => expect(mockListeners.has('voice-ptt-context')).toBe(true));

    const payload = {
      screenshot: 'base64data',
      windowTitle: 'VS Code',
      extractedText: 'some code',
      timestamp: Date.now(),
    };
    mockListeners.get('voice-ptt-context')!({ payload });

    const dispatched = dispatchSpy.mock.calls.find(
      (call) => (call[0] as CustomEvent).type === 'voice-ptt-context',
    );
    expect(dispatched).toBeDefined();
    expect((dispatched![0] as CustomEvent).detail).toEqual(payload);
    expect((dispatched![0] as CustomEvent).cancelable).toBe(true);

    dispatchSpy.mockRestore();
  });

  it('forwards empty screenshot in voice-ptt-context payload faithfully', async () => {
    mockIsTauriRuntime = true;
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    renderHook(() => useVoicePttListener());

    await vi.waitFor(() => expect(mockListeners.has('voice-ptt-context')).toBe(true));

    const payload = {
      screenshot: '',
      windowTitle: 'Terminal',
      extractedText: '',
      timestamp: 1000,
    };
    mockListeners.get('voice-ptt-context')!({ payload });

    const dispatched = dispatchSpy.mock.calls.find(
      (call) => (call[0] as CustomEvent).type === 'voice-ptt-context',
    );
    expect(dispatched).toBeDefined();
    expect((dispatched![0] as CustomEvent).detail).toEqual(payload);

    dispatchSpy.mockRestore();
  });

  it('handles rapid sequential context events without errors', async () => {
    mockIsTauriRuntime = true;
    const dispatchSpy = vi.spyOn(window, 'dispatchEvent');
    renderHook(() => useVoicePttListener());

    await vi.waitFor(() => expect(mockListeners.has('voice-ptt-context')).toBe(true));

    for (let i = 0; i < 5; i++) {
      mockListeners.get('voice-ptt-context')!({
        payload: { screenshot: `img${i}`, windowTitle: `Win${i}`, extractedText: '', timestamp: i },
      });
    }

    const contextEvents = dispatchSpy.mock.calls.filter(
      (call) => (call[0] as CustomEvent).type === 'voice-ptt-context',
    );
    expect(contextEvents).toHaveLength(5);

    dispatchSpy.mockRestore();
  });

  it('unregisters all listeners on unmount', async () => {
    mockIsTauriRuntime = true;
    const { unmount } = renderHook(() => useVoicePttListener());

    await vi.waitFor(() => expect(mockListeners.size).toBe(3));

    unmount();
    expect(mockUnlisten).toHaveBeenCalledTimes(3);
  });
});
