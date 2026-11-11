/** @vitest-environment jsdom */
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType, type AgentStreamEvent, type Message } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import { settle } from '@/test-utils/fakeClock';

import { useAsyncAgentStream } from '../useAsyncAgentStream';

type HandleMessageStream = typeof import('@/store/chat/messageStreamHandler').handleMessageStream;

const mocks = vi.hoisted(() => ({ handleMessageStream: vi.fn<HandleMessageStream>() }));

vi.mock('@/store/chat/messageStreamHandler', () => ({ handleMessageStream: mocks.handleMessageStream }));

const chunk = (label: string): AgentStreamEvent => ({
  type: AgentEventType.AGENT_CANCELLED,
  messageId: `m-${label}`,
  data: label,
});

const arrive = (sessionId: string, event: AgentStreamEvent) =>
  act(() => {
    window.dispatchEvent(
      new CustomEvent('async-agent-stream-chunk', { detail: { session_id: sessionId, chunk: event } }),
    );
  });

const handledChunks = () => mocks.handleMessageStream.mock.calls.map(([event]) => event);

/** Lets the handler's dynamic import and the follow-up timer tick settle before asserting that nothing ran. */
const settleTwice = async () => {
  await settle();
  await settle();
};

describe('useAsyncAgentStream', () => {
  beforeEach(() => {
    mocks.handleMessageStream.mockReset();
    mocks.handleMessageStream.mockResolvedValue({ added: true, recievedMessage: '' });
    useChatStore.setState({ loading: false, messageAppeared: false, messages: [] });
  });

  it('hands a chunk of its own session to the stream handler as a background run', async () => {
    renderHook(() => useAsyncAgentStream('chat-1'));
    const event = chunk('a');

    arrive('chat-1', event);

    await waitFor(() => expect(mocks.handleMessageStream).toHaveBeenCalledTimes(1));
    expect(mocks.handleMessageStream).toHaveBeenCalledWith(
      event,
      '',
      undefined,
      true,
      '',
      expect.objectContaining({ chatId: 'chat-1', loading: false, messages: [] }),
      expect.objectContaining({ setLoading: expect.any(Function), setMessageAppeared: expect.any(Function) }),
    );
  });

  it('lets the handler drive the messages, the loading flag and the message-appeared flag of the store', async () => {
    renderHook(() => useAsyncAgentStream('chat-1'));
    arrive('chat-1', chunk('a'));
    await waitFor(() => expect(mocks.handleMessageStream).toHaveBeenCalledTimes(1));
    const actions = mocks.handleMessageStream.mock.calls[0][6];
    const reply: Message = {
      messageId: 'm-reply',
      chatId: 'chat-1',
      createdAt: new Date(0),
      content: 'done in the background',
      role: 'assistant',
    };

    actions.setMessages((draft) => {
      draft.messages = [reply];
    });
    actions.setLoading(true);
    actions.setMessageAppeared(true);

    expect(useChatStore.getState()).toMatchObject({ messages: [reply], loading: true, messageAppeared: true });
  });

  it('ignores chunks that belong to another session', async () => {
    renderHook(() => useAsyncAgentStream('chat-1'));

    arrive('chat-2', chunk('a'));
    await settleTwice();

    expect(mocks.handleMessageStream).not.toHaveBeenCalled();
  });

  it('keeps chunks back while the user turn streams, then replays them in arrival order once it ends', async () => {
    useChatStore.setState({ loading: true });
    renderHook(() => useAsyncAgentStream('chat-1'));
    const first = chunk('a');
    const second = chunk('b');

    arrive('chat-1', first);
    arrive('chat-1', second);
    await settleTwice();
    expect(mocks.handleMessageStream).not.toHaveBeenCalled();

    act(() => useChatStore.setState({ loading: false }));

    await waitFor(() => expect(handledChunks()).toEqual([first, second]));
  });

  it('has nothing to replay when the user turn ends with no chunk waiting', async () => {
    useChatStore.setState({ loading: true });
    renderHook(() => useAsyncAgentStream('chat-1'));

    act(() => useChatStore.setState({ loading: false }));
    await settleTwice();

    expect(mocks.handleMessageStream).not.toHaveBeenCalled();
  });

  it('follows the session it is given', async () => {
    const { rerender } = renderHook(({ id }) => useAsyncAgentStream(id), { initialProps: { id: 'chat-1' } });
    const current = chunk('new');

    rerender({ id: 'chat-2' });
    arrive('chat-1', chunk('old'));
    arrive('chat-2', current);

    await waitFor(() => expect(handledChunks()).toEqual([current]));
  });

  it('takes no more chunks once unmounted, and replays nothing it was holding', async () => {
    useChatStore.setState({ loading: true });
    const { unmount } = renderHook(() => useAsyncAgentStream('chat-1'));
    arrive('chat-1', chunk('held'));

    unmount();
    arrive('chat-1', chunk('late'));
    act(() => useChatStore.setState({ loading: false }));
    await settleTwice();

    expect(mocks.handleMessageStream).not.toHaveBeenCalled();
  });
});
