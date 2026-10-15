/** @vitest-environment jsdom */
/**
 * stopMessage must stop a turn whose abort handle lives in the chat store even when the chat is shown in a pane.
 *
 * Real scenario: a turn starts in the plain chat view, so only the chat store holds its AbortController.
 * While it streams, the user opens the same chat in a workspace pane and presses Stop. The pane never
 * received a controller of its own; the stop must fall through to the store controller instead of doing nothing.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { cancelActiveChatAgent, cancelAgentRequest } from '@/services/chat';
import useChatStore from '@/store/useChatStore';
import useWorkspaceStore from '@/store/useWorkspaceStore';

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
  useChatStore.setState({
    chatId: 'chat-1',
    currentSessionMessageId: 'msg-1',
    messages: [],
    loading: true,
    abortController: new AbortController(),
    messageAppeared: false,
  });
  useWorkspaceStore.setState({ panes: [{ chatId: 'chat-1', id: 'pane-1' } as never] });
});

describe('stopMessage for a chat shown in a pane', () => {
  it('falls through to the chat controller when the pane holds none', () => {
    const chatController = useChatStore.getState().abortController;

    useChatStore.getState().stopMessage();

    expect(chatController?.signal.aborted).toBe(true);
    expect(cancelActiveChatAgent).toHaveBeenCalledExactlyOnceWith('chat-1');
    expect(cancelAgentRequest).not.toHaveBeenCalled();
    expect(useChatStore.getState().loading).toBe(false);
    expect(useChatStore.getState().abortController).toBeNull();
  });

  it('stops through the pane controller and does not cancel a second time at chat level', () => {
    const paneController = new AbortController();
    useWorkspaceStore.getState().setPaneAbortController('pane-1', paneController);
    useWorkspaceStore.getState().setPaneCurrentSessionMessageId('pane-1', 'msg-1');

    useChatStore.getState().stopMessage();

    expect(paneController.signal.aborted).toBe(true);
    expect(cancelAgentRequest).toHaveBeenCalledExactlyOnceWith('msg-1');
    expect(cancelActiveChatAgent).not.toHaveBeenCalled();
    expect(useWorkspaceStore.getState().getPaneAbortController('pane-1')).toBeNull();
    expect(useChatStore.getState().loading).toBe(false);
  });

  it('does nothing when neither the pane nor the chat holds a controller', () => {
    useChatStore.setState({ abortController: null, loading: false });

    useChatStore.getState().stopMessage();

    expect(cancelActiveChatAgent).not.toHaveBeenCalled();
    expect(cancelAgentRequest).not.toHaveBeenCalled();
    expect(useChatStore.getState().loading).toBe(false);
  });
});
