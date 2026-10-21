import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';

const startChatTurnPrewarm = vi.fn();
const cancelChatTurnPrewarm = vi.fn();

vi.mock('@/services/chat', () => ({
  startChatTurnPrewarm: (...args: unknown[]) => startChatTurnPrewarm(...args),
  cancelChatTurnPrewarm: (...args: unknown[]) => cancelChatTurnPrewarm(...args),
}));

const chatState = {
  chatId: 'c-123',
  actionMode: 'agent' as string,
  incognitoMode: false,
  agentConfig: { agentId: 'builtin-default' },
};

vi.mock('@/store/useChatStore', () => ({
  default: (selector: (state: typeof chatState) => unknown) => selector(chatState),
}));

import { resetTurnPrewarmInflightForTests, useChatTurnPrewarm } from '../useChatTurnPrewarm';

describe('useChatTurnPrewarm', () => {
  beforeEach(() => {
    resetTurnPrewarmInflightForTests();
    startChatTurnPrewarm.mockReset();
    cancelChatTurnPrewarm.mockReset();
    startChatTurnPrewarm.mockResolvedValue({ started: true, chat_id: 'c-123' });
    cancelChatTurnPrewarm.mockResolvedValue({ cancelled: true, chat_id: 'c-123' });
    chatState.actionMode = 'agent';
    chatState.incognitoMode = false;
  });

  it('autoOnMount triggers prewarm for agent mode', async () => {
    renderHook(() => useChatTurnPrewarm({ autoOnMount: true }));

    await waitFor(() => {
      expect(startChatTurnPrewarm).toHaveBeenCalledWith('c-123', {
        agentId: 'builtin-default',
        actionMode: 'agent',
        incognitoMode: false,
      });
    });
  });

  it('skips prewarm in fast mode', async () => {
    chatState.actionMode = 'fast';
    renderHook(() => useChatTurnPrewarm({ autoOnMount: true }));

    await waitFor(() => {
      expect(startChatTurnPrewarm).not.toHaveBeenCalled();
    });
  });

  it('dedupes concurrent triggers across separate hook instances', async () => {
    const { result: hookA } = renderHook(() => useChatTurnPrewarm());
    const { result: hookB } = renderHook(() => useChatTurnPrewarm());

    await Promise.all([hookA.current.triggerPrewarm(), hookB.current.triggerPrewarm()]);

    expect(startChatTurnPrewarm).toHaveBeenCalledTimes(1);
  });

  it('autoOnMount does not cancel prewarm on unmount', async () => {
    const { unmount } = renderHook(() => useChatTurnPrewarm({ autoOnMount: true }));

    await waitFor(() => {
      expect(startChatTurnPrewarm).toHaveBeenCalledTimes(1);
    });

    unmount();

    expect(cancelChatTurnPrewarm).not.toHaveBeenCalled();
  });
});
