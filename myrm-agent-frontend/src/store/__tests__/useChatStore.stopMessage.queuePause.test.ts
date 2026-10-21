/** @vitest-environment jsdom */
/**
 * stopMessage must pause the stopped chat's message queue.
 *
 * Real scenario: the user queued two follow-ups while the agent worked, then pressed Stop because the
 * turn went the wrong way. Without the pause, the first queued message would be sent into the stopped
 * chat the moment the agent turns idle - the opposite of "stop".
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';
import { useMessageQueueStore } from '@/store/chat/useMessageQueueStore';

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

const queueOf = (chatId: string) => useMessageQueueStore.getState().queues[chatId];

beforeEach(() => {
  useMessageQueueStore.setState({ queues: {} });
  const queue = useMessageQueueStore.getState();
  queue.enqueue('chat-1', { text: 'first follow-up', files: [] });
  queue.enqueue('chat-1', { text: 'second follow-up', files: [] });
  queue.enqueue('chat-2', { text: 'message of another chat', files: [] });

  useChatStore.setState({
    chatId: 'chat-1',
    currentSessionMessageId: 'msg-1',
    messages: [],
    loading: true,
    abortController: new AbortController(),
    messageAppeared: false,
  });
  useWorkspaceStore.setState({ panes: [] });
});

describe('stopMessage queue pause', () => {
  it('pauses only the stopped chat and keeps every queued message', () => {
    expect(queueOf('chat-1').pausedReason).toBeNull();

    useChatStore.getState().stopMessage();

    expect(queueOf('chat-1').pausedReason).toBe('stopped');
    expect(queueOf('chat-1').items.map((item) => item.text)).toEqual(['first follow-up', 'second follow-up']);
    expect(queueOf('chat-2').pausedReason).toBeNull();
  });

  it('pauses the queue when the chat runs in a workspace pane', () => {
    useWorkspaceStore.setState({ panes: [{ chatId: 'chat-1', id: 'pane-1' } as never] });
    useWorkspaceStore.getState().setPaneAbortController('pane-1', new AbortController());
    useWorkspaceStore.getState().setPaneCurrentSessionMessageId('pane-1', 'msg-1');

    useChatStore.getState().stopMessage();

    expect(queueOf('chat-1').pausedReason).toBe('stopped');
    expect(queueOf('chat-2').pausedReason).toBeNull();
  });

  it('leaves the queue running when there is no turn to stop', () => {
    useChatStore.setState({ abortController: null, loading: false });

    useChatStore.getState().stopMessage();

    expect(queueOf('chat-1').pausedReason).toBeNull();
  });

  it('does not leave a pause marker behind an empty queue', () => {
    useMessageQueueStore.getState().clearQueue('chat-1');

    useChatStore.getState().stopMessage();

    expect(queueOf('chat-1')?.pausedReason ?? null).toBeNull();
  });
});
