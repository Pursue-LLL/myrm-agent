import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest';
import { handleWakePhaseTransition, setupDesktopWakeRecovery, type WakeEventPayload } from '../desktopWakeRecovery';
import * as deployMode from '@/lib/deploy-mode';
import { cancelActiveChatAgent, getChatDetail, getMessages } from '@/services/chat';
import useChatStore from '@/store/useChatStore';

vi.mock('@/services/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/chat')>();
  return { ...actual, cancelActiveChatAgent: vi.fn(), getChatDetail: vi.fn(), getMessages: vi.fn() };
});

vi.mock('@/services/i18nToastService', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/i18nToastService')>();
  return { ...actual, showI18nToast: vi.fn() };
});

vi.mock('@/lib/inspector/releaseTurnInspectorControls', () => ({
  releaseTurnInspectorControls: vi.fn().mockResolvedValue(undefined),
}));

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

    it('handles phase "ready" by re-syncing a loading session that owns no turn, refreshing history, and syncing background tasks', async () => {
      const loadMessages = vi.fn().mockResolvedValue(undefined);
      const loadChatHistory = vi.fn().mockResolvedValue(undefined);
      const setLoading = vi.fn();
      const notifyBackgroundTasks = vi.fn();

      const mockState = {
        chatId: 'chat-active',
        loading: true,
        abortController: null,
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
      // loadMessages releases the loading flag once the transcript is reconciled; the wake handler never clears it.
      expect(setLoading).not.toHaveBeenCalled();
      expect(loadChatHistory).toHaveBeenCalledWith(1);
      expect(notifyBackgroundTasks).toHaveBeenCalledTimes(1);
    });

    it('leaves a running turn alone: a loading session that owns an abort controller is neither re-synced nor released', async () => {
      const turn = new AbortController();
      const loadMessages = vi.fn().mockResolvedValue(undefined);
      const loadChatHistory = vi.fn().mockResolvedValue(undefined);
      const setLoading = vi.fn();
      const notifyBackgroundTasks = vi.fn();

      const mockState = {
        chatId: 'chat-live',
        loading: true,
        abortController: turn,
        loadMessages,
        loadChatHistory,
        setLoading,
      };

      await handleWakePhaseTransition(
        { phase: 'ready', timestamp: Date.now(), sidecar_alive: true },
        {
          getState: () => mockState as unknown as ReturnType<typeof useChatStore.getState>,
          notifyBackgroundTasks,
        },
      );

      expect(loadMessages).not.toHaveBeenCalled();
      expect(setLoading).not.toHaveBeenCalled();
      expect(turn.signal.aborted).toBe(false);
      expect(loadChatHistory).toHaveBeenCalledWith(1);
      expect(notifyBackgroundTasks).toHaveBeenCalledTimes(1);
    });

    it('keeps refreshing history and background tasks when re-syncing the messages throws', async () => {
      const loadMessages = vi.fn().mockRejectedValue(new Error('Network offline'));
      const loadChatHistory = vi.fn().mockResolvedValue(undefined);
      const setLoading = vi.fn();
      const notifyBackgroundTasks = vi.fn();

      const mockState = {
        chatId: 'chat-flaky',
        loading: true,
        abortController: null,
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

      expect(loadMessages).toHaveBeenCalledWith('chat-flaky');
      expect(setLoading).not.toHaveBeenCalled();
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

  // The real store and the real loadMessages; only the network is replaced.
  describe('against the real chat store', () => {
    const CHAT_ID = 'chat-wake-store';
    const READY: WakeEventPayload = { phase: 'ready', timestamp: 0, sidecar_alive: true };
    const answeredTranscript = (): unknown[] => [
      { messageId: 'u-1', chatId: CHAT_ID, createdAt: new Date(), role: 'user', content: 'question', metadata: {} },
      { messageId: 'a-1', chatId: CHAT_ID, createdAt: new Date(), role: 'assistant', content: 'answer', metadata: {} },
    ];
    const wake = () =>
      handleWakePhaseTransition(READY, { getState: useChatStore.getState, notifyBackgroundTasks: vi.fn() });

    beforeEach(() => {
      vi.spyOn(console, 'error').mockImplementation(() => undefined);
      vi.spyOn(console, 'warn').mockImplementation(() => undefined);
      vi.spyOn(console, 'log').mockImplementation(() => undefined);
      vi.mocked(getChatDetail)
        .mockReset()
        .mockResolvedValue({
          chat: {
            agent_id: null,
            workspace_dir: null,
            actionMode: 'agent',
            is_incognito: false,
            compacted_summary: null,
            compacted_before_id: null,
            session_loaded_skill_names: null,
          },
        } as never);
      vi.mocked(getMessages)
        .mockReset()
        .mockResolvedValue({ messages: answeredTranscript(), has_more: false, next_cursor: null } as never);
      vi.mocked(cancelActiveChatAgent).mockReset().mockResolvedValue({ cancelled: true, chat_id: CHAT_ID });
      useChatStore.setState({
        chatId: CHAT_ID,
        messages: [],
        loading: false,
        abortController: null,
        currentSessionMessageId: null,
        loadChatHistory: vi.fn().mockResolvedValue(undefined),
      });
    });

    afterEach(() => {
      vi.useRealTimers();
    });

    it('re-syncs a residual loading flag that owns no turn, and the real loadMessages releases it', async () => {
      useChatStore.setState({ loading: true });

      await wake();

      expect(getMessages).toHaveBeenCalledWith(CHAT_ID, expect.anything());
      expect(useChatStore.getState().loading).toBe(false);
      expect(useChatStore.getState().messages.map((message) => message.messageId)).toEqual(['u-1', 'a-1']);
    });

    it('still ends with the loading flag released when the re-sync cannot reach the backend', async () => {
      vi.useFakeTimers();
      vi.mocked(getMessages).mockRejectedValue(new Error('backend unreachable'));
      useChatStore.setState({ loading: true });

      const waking = wake();
      // loadMessages retries the failed fetch with a growing delay before it gives up.
      await vi.advanceTimersByTimeAsync(5_000);
      await waking;

      expect(getMessages).toHaveBeenCalledTimes(3);
      expect(useChatStore.getState().loading).toBe(false);
      expect(useChatStore.getState().loadError).toBe(true);
    });

    it('leaves a running turn untouched, and Stop still reaches it afterwards', async () => {
      const turn = new AbortController();
      useChatStore.setState({ loading: true, abortController: turn, currentSessionMessageId: 'a-live' });

      await wake();

      expect(useChatStore.getState().loading).toBe(true);
      expect(useChatStore.getState().abortController).toBe(turn);
      expect(turn.signal.aborted).toBe(false);
      expect(getMessages).not.toHaveBeenCalled();

      useChatStore.getState().stopMessage();

      expect(turn.signal.aborted).toBe(true);
      expect(useChatStore.getState().loading).toBe(false);
      expect(cancelActiveChatAgent).toHaveBeenCalledWith(CHAT_ID);
    });
  });
});
