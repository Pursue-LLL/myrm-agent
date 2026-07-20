/** @vitest-environment jsdom */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

let mockIsTauriRuntime = false;
vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => mockIsTauriRuntime,
  isLocalMode: () => true,
  getDeployMode: () => 'tauri',
}));

const mockOpenInline = vi.fn();
vi.mock('@/store/useFlowPadStore', () => ({
  useFlowPadStore: (selector: (state: { openInline: typeof mockOpenInline }) => unknown) =>
    selector({ openInline: mockOpenInline }),
}));

interface InlineInputPayload {
  screenshot: string;
  windowTitle: string;
  extractedText: string;
  selectedText?: string;
  sourcePid: number;
  timestamp: number;
}

type ListenCallback<T> = (event: { payload: T }) => void;
const mockListeners = new Map<string, ListenCallback<unknown>>();
const mockUnlisten = vi.fn();
const mockListen = vi.fn(async (eventName: string, callback: ListenCallback<unknown>) => {
  mockListeners.set(eventName, callback);
  return mockUnlisten;
});

vi.mock('@tauri-apps/api/event', () => ({
  listen: (...args: [string, ListenCallback<unknown>]) => mockListen(...args),
}));

import { useInlineInputListener } from '../useInlineInputListener';

describe('useInlineInputListener', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockListeners.clear();
    mockIsTauriRuntime = false;
    mockListen.mockReset();
    mockListen.mockImplementation(async (eventName: string, callback: ListenCallback<unknown>) => {
      mockListeners.set(eventName, callback);
      return mockUnlisten;
    });
  });

  afterEach(() => {
    mockIsTauriRuntime = false;
  });

  it('does not register listener in non-Tauri environment', () => {
    mockIsTauriRuntime = false;
    renderHook(() => useInlineInputListener());
    expect(mockListeners.size).toBe(0);
  });

  it('registers inline-input-activated listener in Tauri runtime', async () => {
    mockIsTauriRuntime = true;
    renderHook(() => useInlineInputListener());

    await vi.waitFor(() => {
      expect(mockListeners.has('inline-input-activated')).toBe(true);
    });
  });

  it('opens FlowPad inline mode with payload data', async () => {
    mockIsTauriRuntime = true;
    renderHook(() => useInlineInputListener());

    await vi.waitFor(() => {
      expect(mockListeners.has('inline-input-activated')).toBe(true);
    });

    const payload: InlineInputPayload = {
      screenshot: 'base64data',
      windowTitle: 'Slack',
      extractedText: 'draft message',
      selectedText: 'hello world',
      sourcePid: 321,
      timestamp: 1700000000000,
    };

    act(() => {
      mockListeners.get('inline-input-activated')!({ payload });
    });

    expect(mockOpenInline).toHaveBeenCalledWith(
      {
        screenshot: 'base64data',
        windowTitle: 'Slack',
        extractedText: 'draft message',
        selectedText: 'hello world',
        timestamp: 1700000000000,
      },
      321,
    );
  });

  it('normalizes empty selectedText to undefined', async () => {
    mockIsTauriRuntime = true;
    renderHook(() => useInlineInputListener());

    await vi.waitFor(() => {
      expect(mockListeners.has('inline-input-activated')).toBe(true);
    });

    act(() => {
      mockListeners.get('inline-input-activated')!({
        payload: {
          screenshot: 'base64data',
          windowTitle: 'Terminal',
          extractedText: 'cmd output',
          selectedText: '',
          sourcePid: 999,
          timestamp: 1700000000001,
        } satisfies InlineInputPayload,
      });
    });

    expect(mockOpenInline).toHaveBeenCalledWith(
      {
        screenshot: 'base64data',
        windowTitle: 'Terminal',
        extractedText: 'cmd output',
        selectedText: undefined,
        timestamp: 1700000000001,
      },
      999,
    );
  });

  it('unregisters listener on unmount', async () => {
    mockIsTauriRuntime = true;
    const { unmount } = renderHook(() => useInlineInputListener());

    await vi.waitFor(() => {
      expect(mockListeners.has('inline-input-activated')).toBe(true);
    });

    unmount();
    expect(mockUnlisten).toHaveBeenCalledTimes(1);
  });

  it('still disposes listener when unmounted before async listen resolves', async () => {
    mockIsTauriRuntime = true;
    let resolveListen: ((dispose: () => void) => void) | null = null;
    mockListen.mockImplementationOnce(async (eventName: string, callback: ListenCallback<unknown>) => {
      mockListeners.set(eventName, callback);
      return await new Promise<() => void>((resolve) => {
        resolveListen = resolve;
      });
    });

    const { unmount } = renderHook(() => useInlineInputListener());
    await vi.waitFor(() => {
      expect(mockListen).toHaveBeenCalledTimes(1);
    });

    unmount();

    const lateUnlisten = vi.fn();
    resolveListen?.(lateUnlisten);

    await vi.waitFor(() => {
      expect(lateUnlisten).toHaveBeenCalledTimes(1);
    });
  });
});
