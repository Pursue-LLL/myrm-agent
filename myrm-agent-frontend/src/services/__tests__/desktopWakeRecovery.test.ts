import { describe, expect, it, vi, beforeEach } from 'vitest';
import { handleWakePhaseTransition, setupDesktopWakeRecovery, type WakeEventPayload } from '../desktopWakeRecovery';
import * as deployMode from '@/lib/deploy-mode';
import useChatStore from '@/store/useChatStore';

describe('desktopWakeRecovery', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe('handleWakePhaseTransition', () => {
    it('handles phase "waking" silently without triggering network side effects', async () => {
      const mockState = {
        chatId: 'chat-123',
        loading: false,
        loadMessages: vi.fn(),
        loadChatHistory: vi.fn(),
        setLoading: vi.fn(),
      };
      const notifyBackgroundTasks = vi.fn();

      const payload: WakeEventPayload = {
        phase: 'waking',
        timestamp: Date.now(),
        reason: 'wall_clock_drift',
      };

      await handleWakePhaseTransition(payload, {
        getState: () => mockState as unknown as ReturnType<typeof useChatStore.getState>,
        notifyBackgroundTasks,
      });

      expect(mockState.loadMessages).not.toHaveBeenCalled();
      expect(mockState.loadChatHistory).not.toHaveBeenCalled();
      expect(notifyBackgroundTasks).not.toHaveBeenCalled();
    });

    it('handles phase "ready" by recovering stuck loading session, refreshing history, and syncing background tasks', async () => {
      const loadMessages = vi.fn().mockResolvedValue(undefined);
      const loadChatHistory = vi.fn().mockResolvedValue(undefined);
      const setLoading = vi.fn();
      const notifyBackgroundTasks = vi.fn();

      const mockState = {
        chatId: 'chat-active',
        loading: true,
        loadMessages,
        loadChatHistory,
        setLoading,
      };

      const payload: WakeEventPayload = {
        phase: 'ready',
        timestamp: Date.now(),
        sidecar_alive: true,
        reason: 'wall_clock_drift',
      };

      await handleWakePhaseTransition(payload, {
        getState: () => mockState as unknown as ReturnType<typeof useChatStore.getState>,
        notifyBackgroundTasks,
      });

      expect(loadMessages).toHaveBeenCalledWith('chat-active');
      expect(setLoading).toHaveBeenCalledWith(false);
      expect(loadChatHistory).toHaveBeenCalledWith(1);
      expect(notifyBackgroundTasks).toHaveBeenCalledTimes(1);
    });

    it('guarantees setLoading(false) even if loadMessages throws on network recovery lag', async () => {
      const loadMessages = vi.fn().mockRejectedValue(new Error('Network offline'));
      const loadChatHistory = vi.fn().mockResolvedValue(undefined);
      const setLoading = vi.fn();
      const notifyBackgroundTasks = vi.fn();

      const mockState = {
        chatId: 'chat-flaky',
        loading: true,
        loadMessages,
        loadChatHistory,
        setLoading,
      };

      const payload: WakeEventPayload = {
        phase: 'ready',
        timestamp: Date.now(),
        sidecar_alive: true,
      };

      await handleWakePhaseTransition(payload, {
        getState: () => mockState as unknown as ReturnType<typeof useChatStore.getState>,
        notifyBackgroundTasks,
      });

      expect(setLoading).toHaveBeenCalledWith(false);
      expect(loadChatHistory).toHaveBeenCalledWith(1);
      expect(notifyBackgroundTasks).toHaveBeenCalledTimes(1);
    });

    it('skips message recovery if no active chat or not loading', async () => {
      const loadMessages = vi.fn();
      const loadChatHistory = vi.fn().mockResolvedValue(undefined);
      const setLoading = vi.fn();
      const notifyBackgroundTasks = vi.fn();

      const mockState = {
        chatId: undefined,
        loading: false,
        loadMessages,
        loadChatHistory,
        setLoading,
      };

      const payload: WakeEventPayload = {
        phase: 'ready',
        timestamp: Date.now(),
        sidecar_alive: true,
      };

      await handleWakePhaseTransition(payload, {
        getState: () => mockState as unknown as ReturnType<typeof useChatStore.getState>,
        notifyBackgroundTasks,
      });

      expect(loadMessages).not.toHaveBeenCalled();
      expect(setLoading).not.toHaveBeenCalled();
      expect(loadChatHistory).toHaveBeenCalledWith(1);
      expect(notifyBackgroundTasks).toHaveBeenCalledTimes(1);
    });

    it('handles loadChatHistory failure gracefully and still executes background task sync', async () => {
      const loadChatHistory = vi.fn().mockRejectedValue(new Error('History service unavailable'));
      const notifyBackgroundTasks = vi.fn();

      const mockState = {
        chatId: undefined,
        loading: false,
        loadMessages: vi.fn(),
        loadChatHistory,
        setLoading: vi.fn(),
      };

      const payload: WakeEventPayload = {
        phase: 'ready',
        timestamp: Date.now(),
        sidecar_alive: true,
      };

      await expect(
        handleWakePhaseTransition(payload, {
          getState: () => mockState as unknown as ReturnType<typeof useChatStore.getState>,
          notifyBackgroundTasks,
        }),
      ).resolves.toBeUndefined();

      expect(loadChatHistory).toHaveBeenCalledWith(1);
      expect(notifyBackgroundTasks).toHaveBeenCalledTimes(1);
    });

    it('handles notifyBackgroundTasks failure gracefully without rethrowing', async () => {
      const notifyBackgroundTasks = vi.fn().mockImplementation(() => {
        throw new Error('Background task bus dropped');
      });

      const mockState = {
        chatId: undefined,
        loading: false,
        loadMessages: vi.fn(),
        loadChatHistory: vi.fn().mockResolvedValue(undefined),
        setLoading: vi.fn(),
      };

      const payload: WakeEventPayload = {
        phase: 'ready',
        timestamp: Date.now(),
        sidecar_alive: true,
      };

      await expect(
        handleWakePhaseTransition(payload, {
          getState: () => mockState as unknown as ReturnType<typeof useChatStore.getState>,
          notifyBackgroundTasks,
        }),
      ).resolves.toBeUndefined();

      expect(notifyBackgroundTasks).toHaveBeenCalledTimes(1);
    });
  });

  describe('setupDesktopWakeRecovery in Web mode', () => {
    it('ignores quick window blur/focus below 10s threshold in browser', async () => {
      vi.spyOn(deployMode, 'isTauriRuntime').mockReturnValue(false);
      const loadChatHistory = vi.fn().mockResolvedValue(undefined);
      vi.spyOn(useChatStore, 'getState').mockReturnValue({
        chatId: 'chat-web',
        loading: false,
        loadMessages: vi.fn(),
        loadChatHistory,
        setLoading: vi.fn(),
      } as unknown as ReturnType<typeof useChatStore.getState>);

      const unlisten = await setupDesktopWakeRecovery();

      // 切到后台
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));

      // 仅过 1 秒切回前台（快速切窗口）
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));

      expect(loadChatHistory).not.toHaveBeenCalled();

      unlisten();
    });

    it('triggers recovery after 10s or longer background suspension in browser', async () => {
      vi.spyOn(deployMode, 'isTauriRuntime').mockReturnValue(false);
      const loadChatHistory = vi.fn().mockResolvedValue(undefined);
      vi.spyOn(useChatStore, 'getState').mockReturnValue({
        chatId: 'chat-web',
        loading: false,
        loadMessages: vi.fn(),
        loadChatHistory,
        setLoading: vi.fn(),
      } as unknown as ReturnType<typeof useChatStore.getState>);

      const unlisten = await setupDesktopWakeRecovery();

      let currentTime = 100_000;
      const dateSpy = vi.spyOn(Date, 'now').mockImplementation(() => currentTime);

      // 切到后台
      Object.defineProperty(document, 'visibilityState', { value: 'hidden', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));

      // 经历 12 秒睡眠挂起后恢复
      currentTime += 12_000;
      Object.defineProperty(document, 'visibilityState', { value: 'visible', configurable: true });
      document.dispatchEvent(new Event('visibilitychange'));

      await Promise.resolve();
      expect(loadChatHistory).toHaveBeenCalledWith(1);

      dateSpy.mockRestore();
      unlisten();
    });

    it('triggers recovery on browser online event and stops listening after unlisten', async () => {
      vi.spyOn(deployMode, 'isTauriRuntime').mockReturnValue(false);
      const loadChatHistory = vi.fn().mockResolvedValue(undefined);
      vi.spyOn(useChatStore, 'getState').mockReturnValue({
        chatId: 'chat-web',
        loading: false,
        loadMessages: vi.fn(),
        loadChatHistory,
        setLoading: vi.fn(),
      } as unknown as ReturnType<typeof useChatStore.getState>);

      const unlisten = await setupDesktopWakeRecovery();

      window.dispatchEvent(new Event('online'));
      await Promise.resolve();
      expect(loadChatHistory).toHaveBeenCalledTimes(1);

      // 解除监听后再次触发不应有任何反应
      unlisten();
      window.dispatchEvent(new Event('online'));
      await Promise.resolve();
      expect(loadChatHistory).toHaveBeenCalledTimes(1);
    });
  });

  describe('setupDesktopWakeRecovery in Tauri mode', () => {
    it('subscribes to native app:system-wake and handles phase transition', async () => {
      vi.spyOn(deployMode, 'isTauriRuntime').mockReturnValue(true);
      const mockTauriUnlisten = vi.fn();
      let eventHandler: ((event: { payload: WakeEventPayload }) => void) | undefined;

      const loadChatHistory = vi.fn().mockResolvedValue(undefined);
      vi.spyOn(useChatStore, 'getState').mockReturnValue({
        chatId: 'chat-tauri',
        loading: false,
        loadMessages: vi.fn(),
        loadChatHistory,
        setLoading: vi.fn(),
      } as unknown as ReturnType<typeof useChatStore.getState>);

      vi.doMock('@tauri-apps/api/event', () => ({
        listen: vi.fn(async (event: string, cb: (event: { payload: WakeEventPayload }) => void) => {
          if (event === 'app:system-wake') {
            eventHandler = cb;
          }
          return mockTauriUnlisten;
        }),
      }));

      const unlisten = await setupDesktopWakeRecovery();
      expect(typeof unlisten).toBe('function');
      expect(eventHandler).toBeDefined();

      // 模拟 Tauri 触发原生 app:system-wake 事件
      if (eventHandler) {
        eventHandler({
          payload: {
            phase: 'ready',
            timestamp: Date.now(),
            sidecar_alive: true,
          },
        });
      }
      await Promise.resolve();

      expect(loadChatHistory).toHaveBeenCalledWith(1);

      unlisten();
      expect(mockTauriUnlisten).toHaveBeenCalledTimes(1);
    });
  });
});
