import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

let mockIsTauriRuntime = false;
vi.mock('@/lib/deploy-mode', () => ({
  isTauriRuntime: () => mockIsTauriRuntime,
  isLocalMode: () => true,
  getDeployMode: () => 'tauri',
}));

const mockToast = {
  warning: vi.fn(),
  error: vi.fn(),
  success: vi.fn(),
};
vi.mock('@/lib/utils/toast', () => ({
  toast: mockToast,
}));

const mockAddCapture = vi.fn();
const mockGetState = vi.fn(() => ({ captures: [] }));
vi.mock('@/store/useFlowPadStore', () => ({
  useFlowPadStore: Object.assign(
    (selector: (s: { addCapture: typeof mockAddCapture }) => unknown) =>
      selector({ addCapture: mockAddCapture }),
    { getState: mockGetState },
  ),
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

const mockInvoke = vi.fn();
vi.mock('@tauri-apps/api/core', () => ({
  invoke: (...args: unknown[]) => mockInvoke(...args),
}));

describe('useAppshotListener', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    mockListeners.clear();
    mockIsTauriRuntime = true;
    mockGetState.mockReturnValue({ captures: [] });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  async function mountHook() {
    const mod = await import('../useAppshotListener');
    return renderHook(() => mod.useAppshotListener());
  }

  describe('Tauri environment event listening', () => {
    it('registers both appshot-captured and appshot-blocked listeners', async () => {
      await mountHook();
      await vi.dynamicImportSettled();
      await new Promise((r) => setTimeout(r, 50));

      expect(mockListeners.has('appshot-captured')).toBe(true);
      expect(mockListeners.has('appshot-blocked')).toBe(true);
    });

    it('does not register listeners in non-Tauri environment', async () => {
      mockIsTauriRuntime = false;
      await mountHook();
      await vi.dynamicImportSettled();
      await new Promise((r) => setTimeout(r, 50));

      expect(mockListeners.size).toBe(0);
    });
  });

  describe('appshot-captured event handling', () => {
    it('adds capture to FlowPad store on valid payload', async () => {
      await mountHook();
      await vi.dynamicImportSettled();
      await new Promise((r) => setTimeout(r, 50));

      const handler = mockListeners.get('appshot-captured');
      expect(handler).toBeDefined();

      act(() => {
        handler!({
          payload: {
            screenshot: 'base64data',
            windowTitle: 'Test Window',
            extractedText: 'Hello world',
            needsPermission: false,
            timestamp: 1700000000000,
          },
        });
      });

      expect(mockAddCapture).toHaveBeenCalledWith({
        screenshot: 'base64data',
        windowTitle: 'Test Window',
        extractedText: 'Hello world',
        timestamp: 1700000000000,
      });
    });

    it('shows error toast when payload has no screenshot and no text', async () => {
      await mountHook();
      await vi.dynamicImportSettled();
      await new Promise((r) => setTimeout(r, 50));

      const handler = mockListeners.get('appshot-captured');
      act(() => {
        handler!({
          payload: {
            screenshot: '',
            windowTitle: '',
            extractedText: '',
            needsPermission: false,
            timestamp: 1700000000000,
          },
        });
      });

      expect(mockToast.error).toHaveBeenCalledWith('captureFailed', { duration: 3000 });
      expect(mockAddCapture).not.toHaveBeenCalled();
    });

    it('shows permission warning toast when needsPermission is true', async () => {
      await mountHook();
      await vi.dynamicImportSettled();
      await new Promise((r) => setTimeout(r, 50));

      const handler = mockListeners.get('appshot-captured');
      act(() => {
        handler!({
          payload: {
            screenshot: 'data',
            windowTitle: 'App',
            extractedText: '',
            needsPermission: true,
            timestamp: 1700000000000,
          },
        });
      });

      expect(mockToast.warning).toHaveBeenCalledWith(
        'permissionRequired',
        expect.objectContaining({
          duration: 15_000,
          dismissible: true,
        }),
      );
    });
  });

  describe('appshot-blocked event handling (Privacy Blacklist)', () => {
    it('shows warning toast with blocked app name', async () => {
      await mountHook();
      await vi.dynamicImportSettled();
      await new Promise((r) => setTimeout(r, 50));

      const handler = mockListeners.get('appshot-blocked');
      expect(handler).toBeDefined();

      act(() => {
        handler!({
          payload: {
            blockedApp: '1Password',
            timestamp: 1700000000000,
          },
        });
      });

      expect(mockToast.warning).toHaveBeenCalledWith(
        expect.stringContaining('privacyBlocked'),
        expect.objectContaining({
          duration: 8000,
          dismissible: true,
          action: expect.objectContaining({
            label: 'captureAnyway',
          }),
        }),
      );
    });

    it('invokes force_appshot_capture when "Continue Anyway" is clicked', async () => {
      mockInvoke.mockResolvedValue(undefined);
      await mountHook();
      await vi.dynamicImportSettled();
      await new Promise((r) => setTimeout(r, 50));

      const handler = mockListeners.get('appshot-blocked');
      act(() => {
        handler!({
          payload: { blockedApp: 'WeChat', timestamp: 1700000000000 },
        });
      });

      const toastCall = mockToast.warning.mock.calls[0];
      const actionConfig = toastCall[1].action;
      expect(actionConfig.onClick).toBeDefined();

      await act(async () => {
        await actionConfig.onClick();
      });

      expect(mockInvoke).toHaveBeenCalledWith('force_appshot_capture');
    });
  });

  describe('cleanup on unmount', () => {
    it('calls unlisten functions on unmount', async () => {
      const { unmount } = await mountHook();
      await vi.dynamicImportSettled();
      await new Promise((r) => setTimeout(r, 50));

      unmount();
      expect(mockUnlisten).toHaveBeenCalled();
    });
  });
});
