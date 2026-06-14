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

  it('registers voice-ptt-start and voice-ptt-stop listeners in Tauri', async () => {
    mockIsTauriRuntime = true;
    renderHook(() => useVoicePttListener());

    await vi.waitFor(() => {
      expect(mockListeners.has('voice-ptt-start')).toBe(true);
      expect(mockListeners.has('voice-ptt-stop')).toBe(true);
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

  it('unregisters listeners on unmount', async () => {
    mockIsTauriRuntime = true;
    const { unmount } = renderHook(() => useVoicePttListener());

    await vi.waitFor(() => expect(mockListeners.size).toBe(2));

    unmount();
    expect(mockUnlisten).toHaveBeenCalledTimes(2);
  });
});
