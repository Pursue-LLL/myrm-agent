import { describe, expect, it, vi } from 'vitest';
import { handleWakePhaseTransition, type WakeEventPayload } from '../desktopWakeRecovery';

describe('desktopWakeRecovery', () => {
  it('handles phase "waking" by toggling wake recovering state to true', async () => {
    const setWakeRecovering = vi.fn();
    const mockState = {
      setWakeRecovering,
      chatId: 'chat-123',
      loading: false,
      loadMessages: vi.fn(),
      loadChatHistory: vi.fn(),
      setLoading: vi.fn(),
    };

    const payload: WakeEventPayload = {
      phase: 'waking',
      timestamp: Date.now(),
      reason: 'wall_clock_drift',
    };

    await handleWakePhaseTransition(payload, {
      getState: () => mockState as unknown as ReturnType<typeof import('@/store/useChatStore').default.getState>,
    });

    expect(setWakeRecovering).toHaveBeenCalledWith(true);
    expect(mockState.loadMessages).not.toHaveBeenCalled();
  });

  it('handles phase "ready" by recovering stuck loading session and refreshing history', async () => {
    const setWakeRecovering = vi.fn();
    const loadMessages = vi.fn().mockResolvedValue(undefined);
    const loadChatHistory = vi.fn().mockResolvedValue(undefined);
    const setLoading = vi.fn();

    const mockState = {
      setWakeRecovering,
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
    });

    expect(setWakeRecovering).toHaveBeenCalledWith(false);
    expect(loadMessages).toHaveBeenCalledWith('chat-active');
    expect(setLoading).toHaveBeenCalledWith(false);
    expect(loadChatHistory).toHaveBeenCalledWith(1);
  });

  it('guarantees setLoading(false) even if loadMessages throws on network recovery lag', async () => {
    const setWakeRecovering = vi.fn();
    const loadMessages = vi.fn().mockRejectedValue(new Error('Network offline'));
    const loadChatHistory = vi.fn().mockResolvedValue(undefined);
    const setLoading = vi.fn();

    const mockState = {
      setWakeRecovering,
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
    });

    expect(setWakeRecovering).toHaveBeenCalledWith(false);
    expect(setLoading).toHaveBeenCalledWith(false);
    expect(loadChatHistory).toHaveBeenCalledWith(1);
  });

  it('skips message recovery if no active chat or not loading', async () => {
    const setWakeRecovering = vi.fn();
    const loadMessages = vi.fn();
    const loadChatHistory = vi.fn().mockResolvedValue(undefined);
    const setLoading = vi.fn();

    const mockState = {
      setWakeRecovering,
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
    });

    expect(setWakeRecovering).toHaveBeenCalledWith(false);
    expect(loadMessages).not.toHaveBeenCalled();
    expect(setLoading).not.toHaveBeenCalled();
    expect(loadChatHistory).toHaveBeenCalledWith(1);
  });
});
