import { describe, expect, it, vi } from 'vitest';
import { handleWakePhaseTransition, type WakeEventPayload } from '../desktopWakeRecovery';

describe('desktopWakeRecovery', () => {
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
      getState: () => mockState as unknown as ReturnType<typeof import('@/store/useChatStore').default.getState>,
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
      getState: () => mockState as unknown as ReturnType<typeof import('@/store/useChatStore').default.getState>,
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
      getState: () => mockState as unknown as ReturnType<typeof import('@/store/useChatStore').default.getState>,
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
      getState: () => mockState as unknown as ReturnType<typeof import('@/store/useChatStore').default.getState>,
      notifyBackgroundTasks,
    });

    expect(loadMessages).not.toHaveBeenCalled();
    expect(setLoading).not.toHaveBeenCalled();
    expect(loadChatHistory).toHaveBeenCalledWith(1);
    expect(notifyBackgroundTasks).toHaveBeenCalledTimes(1);
  });
});
