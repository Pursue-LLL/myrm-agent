/** @vitest-environment jsdom */
/**
 * stopMessage must reach a turn the server started itself.
 *
 * Real scenario: a background subagent finishes while the chat is idle and the server wakes the agent. This client
 * never sent a message, so it holds no AbortController; Stop has to reach the agent through the server, or the agent
 * keeps working (and spending tokens).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import { useMessageQueueStore } from '@/store/chat/useMessageQueueStore';
import { cancelActiveChatAgent } from '@/services/chat';

vi.mock('@/services/chat', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/chat')>();
  return {
    ...actual,
    cancelAgentRequest: vi.fn().mockResolvedValue(undefined),
    cancelActiveChatAgent: vi.fn().mockResolvedValue(undefined),
  };
});

vi.mock('@/services/i18nToastService', () => ({
  showI18nToast: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  useMessageQueueStore.setState({ queues: {} });
  useMessageQueueStore.getState().enqueue('chat-1', { text: 'typed while the agent woke up', files: [] });
  useChatStore.setState({
    chatId: 'chat-1',
    currentSessionMessageId: null,
    messages: [],
    loading: false,
    abortController: null,
    sessionStatuses: {},
  });
  useWorkspaceStore.setState({ panes: [] });
});

describe('stopMessage on a server-started turn', () => {
  it('cancels the chat by id when the server reports it generating and this client owns no turn', () => {
    useChatStore.getState().setSessionStatus('chat-1', 'generating');

    useChatStore.getState().stopMessage();

    expect(cancelActiveChatAgent).toHaveBeenCalledWith('chat-1');
  });

  it('keeps the queued message from firing into the stopped chat', () => {
    useChatStore.getState().setSessionStatus('chat-1', 'generating');

    useChatStore.getState().stopMessage();

    expect(useMessageQueueStore.getState().queues['chat-1'].pausedReason).toBe('stopped');
  });

  it('does nothing when the chat is idle', () => {
    useChatStore.getState().stopMessage();

    expect(cancelActiveChatAgent).not.toHaveBeenCalled();
    expect(useMessageQueueStore.getState().queues['chat-1'].pausedReason).toBeNull();
  });

  it('does nothing for a turn running in another chat', () => {
    useChatStore.getState().setSessionStatus('chat-2', 'generating');

    useChatStore.getState().stopMessage();

    expect(cancelActiveChatAgent).not.toHaveBeenCalled();
  });
});
