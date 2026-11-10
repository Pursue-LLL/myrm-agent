/**
 * @vitest-environment jsdom
 *
 * [INPUT]
 * - ../ChatWindow (POS: 聊天窗口，监听后台 Agent 流与系统通知)
 * - ./chatWindowMocks (POS: 子组件替身与路由替身)
 *
 * [OUTPUT]
 * Vitest: 后台 Agent 流分片只处理当前会话、用户自己的回合在流式时暂存并按到达顺序补放；
 * 系统通知只对当前会话弹快照提示、刷新转录与目标。
 *
 * [POS]
 * 流处理器、转录刷新、toast 与目标 store 为替身，窗口与聊天 store 为真实实现。
 */
import { act, render, screen, waitFor } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { navigation, openChatInStore } from './chatWindowMocks';
import { AdaptiveScheduler } from '@/store/chat/adaptiveScheduler';
import { useGoalStore } from '@/store/chat/goals/useGoalStore';
import type { AgentStreamEvent } from '@/store/chat/types';
import useChatStore from '@/store/useChatStore';
import ChatWindow from '../ChatWindow';

type HandleMessageStream = typeof import('@/store/chat/messageStreamHandler').handleMessageStream;
type ToastOptions = { title: string; description: ReactNode; variant: string };

const stream = vi.hoisted(() => ({
  handleMessageStream: vi.fn<HandleMessageStream>(),
  refreshTranscript: vi.fn<(chatId: string | undefined) => Promise<void>>(),
  toast: vi.fn<(options: ToastOptions) => void>(),
}));

vi.mock('@/store/chat/messageStreamHandler', () => ({ handleMessageStream: stream.handleMessageStream }));
vi.mock('@/store/chat/chatTranscriptRefresh', () => ({ refreshOpenChatTranscript: stream.refreshTranscript }));
vi.mock('@/hooks/shared/useToast', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/hooks/shared/useToast')>()),
  toast: stream.toast,
}));

const OPEN_CHAT = 'chat-async-1';

function chunk(label: string): AgentStreamEvent {
  return { type: 'async-test', label } as unknown as AgentStreamEvent;
}

function sendChunk(sessionId: string, event: AgentStreamEvent): void {
  window.dispatchEvent(
    new CustomEvent('async-agent-stream-chunk', { detail: { session_id: sessionId, chunk: event } }),
  );
}

function notify(meta: Record<string, unknown>): void {
  act(() => {
    window.dispatchEvent(new CustomEvent('system-notification', { detail: { data: { meta_data: meta } } }));
  });
}

/** Lets the handler's dynamic import and any queued timers run, so "nothing happened" is a real observation. */
async function settle(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 20));
  });
}

function handledChunks(): AgentStreamEvent[] {
  return stream.handleMessageStream.mock.calls.map(([data]) => data);
}

beforeEach(() => {
  vi.clearAllMocks();
  stream.handleMessageStream.mockResolvedValue({ added: true, recievedMessage: '' });
  navigation.searchParams = new URLSearchParams();
  openChatInStore(OPEN_CHAT, { actionMode: 'agent' });
});

describe('ChatWindow background agent stream', () => {
  it('hands a chunk of the open chat to the stream handler as a background chunk of an idle chat', async () => {
    render(<ChatWindow id={OPEN_CHAT} />);
    const event = chunk('first');

    act(() => sendChunk(OPEN_CHAT, event));

    await waitFor(() => expect(stream.handleMessageStream).toHaveBeenCalledOnce());
    const [data, input, sources, added, received, snapshot] = stream.handleMessageStream.mock.calls[0];
    expect([data, input, sources, added, received]).toEqual([event, '', undefined, true, '']);
    expect(snapshot).toMatchObject({ chatId: OPEN_CHAT, actionMode: 'agent', messageAppeared: false, loading: false });
    expect(snapshot.scheduler).toBeInstanceOf(AdaptiveScheduler);
  });

  it('lets the handler write messages, loading and the appeared flag into the chat store', async () => {
    const updateMessages = vi.fn();
    useChatStore.setState({ updateMessages });
    render(<ChatWindow id={OPEN_CHAT} />);

    act(() => sendChunk(OPEN_CHAT, chunk('first')));
    await waitFor(() => expect(stream.handleMessageStream).toHaveBeenCalledOnce());
    const actions = stream.handleMessageStream.mock.calls[0][6];

    act(() => {
      actions.setLoading(true);
      actions.setMessageAppeared(true);
    });
    expect(useChatStore.getState()).toMatchObject({ loading: true, messageAppeared: true });

    const recipe = vi.fn();
    actions.setMessages(recipe);
    expect(updateMessages).toHaveBeenCalledExactlyOnceWith(recipe);
    expect(actions._processSuggestions).toBe(useChatStore.getState()._processSuggestions);
    expect(actions.scheduleAutoSave).toBe(useChatStore.getState().scheduleAutoSave);
  });

  it('ignores chunks that belong to another chat', async () => {
    render(<ChatWindow id={OPEN_CHAT} />);

    act(() => sendChunk('another-chat', chunk('foreign')));
    await settle();

    expect(stream.handleMessageStream).not.toHaveBeenCalled();
  });

  it('plays chunks that arrive together in arrival order on one shared scheduler', async () => {
    render(<ChatWindow id={OPEN_CHAT} />);
    const first = chunk('first');
    const second = chunk('second');

    act(() => {
      sendChunk(OPEN_CHAT, first);
      sendChunk(OPEN_CHAT, second);
    });

    await waitFor(() => expect(stream.handleMessageStream).toHaveBeenCalledTimes(2));
    expect(handledChunks()).toEqual([first, second]);
    const [firstCall, secondCall] = stream.handleMessageStream.mock.calls;
    expect(firstCall[5].scheduler).toBe(secondCall[5].scheduler);
  });

  describe('while the user turn is streaming', () => {
    it('holds chunks and plays them in arrival order once the turn ends', async () => {
      openChatInStore(OPEN_CHAT, { actionMode: 'agent', loading: true });
      render(<ChatWindow id={OPEN_CHAT} />);
      const first = chunk('first');
      const second = chunk('second');

      act(() => {
        sendChunk(OPEN_CHAT, first);
        sendChunk(OPEN_CHAT, second);
      });
      await settle();
      expect(stream.handleMessageStream).not.toHaveBeenCalled();

      act(() => useChatStore.setState({ loading: false }));

      await waitFor(() => expect(stream.handleMessageStream).toHaveBeenCalledTimes(2));
      expect(handledChunks()).toEqual([first, second]);
    });

    it('keeps holding them for store writes that are not the end of the turn', async () => {
      openChatInStore(OPEN_CHAT, { actionMode: 'agent', loading: true });
      render(<ChatWindow id={OPEN_CHAT} />);

      act(() => sendChunk(OPEN_CHAT, chunk('held')));
      act(() => useChatStore.setState({ inputMessage: 'typing', messageAppeared: true }));
      await settle();

      expect(stream.handleMessageStream).not.toHaveBeenCalled();
    });

    it('holds the rest again when the user starts another turn while one chunk is being played', async () => {
      openChatInStore(OPEN_CHAT, { actionMode: 'agent', loading: true });
      render(<ChatWindow id={OPEN_CHAT} />);
      const first = chunk('first');
      const second = chunk('second');
      act(() => {
        sendChunk(OPEN_CHAT, first);
        sendChunk(OPEN_CHAT, second);
      });
      stream.handleMessageStream.mockImplementationOnce(async () => {
        act(() => useChatStore.setState({ loading: true }));
        return { added: true, recievedMessage: '' };
      });

      act(() => useChatStore.setState({ loading: false }));
      await waitFor(() => expect(stream.handleMessageStream).toHaveBeenCalledOnce());
      await settle();
      expect(handledChunks()).toEqual([first]);

      act(() => useChatStore.setState({ loading: false }));
      await waitFor(() => expect(stream.handleMessageStream).toHaveBeenCalledTimes(2));
      expect(handledChunks()).toEqual([first, second]);
    });
  });

  it('follows the open chat: chunks of the previous chat are ignored, those of the new one are played', async () => {
    const { rerender } = render(<ChatWindow id={OPEN_CHAT} />);
    useChatStore.setState({ chatId: 'chat-async-2' });
    rerender(<ChatWindow id="chat-async-2" />);

    act(() => sendChunk(OPEN_CHAT, chunk('old')));
    act(() => sendChunk('chat-async-2', chunk('new')));

    await waitFor(() => expect(stream.handleMessageStream).toHaveBeenCalledOnce());
    expect(stream.handleMessageStream.mock.calls[0][5].chatId).toBe('chat-async-2');
    await settle();
    expect(stream.handleMessageStream).toHaveBeenCalledOnce();
  });

  it('stops listening once unmounted', async () => {
    const { unmount } = render(<ChatWindow id={OPEN_CHAT} />);
    unmount();

    act(() => sendChunk(OPEN_CHAT, chunk('late')));
    await settle();

    expect(stream.handleMessageStream).not.toHaveBeenCalled();
  });

  it('no longer plays held chunks after it is unmounted', async () => {
    openChatInStore(OPEN_CHAT, { actionMode: 'agent', loading: true });
    const { unmount } = render(<ChatWindow id={OPEN_CHAT} />);
    act(() => sendChunk(OPEN_CHAT, chunk('held')));
    unmount();

    useChatStore.setState({ loading: false });
    await settle();

    expect(stream.handleMessageStream).not.toHaveBeenCalled();
  });
});

describe('ChatWindow system notifications', () => {
  const refreshActiveGoal = vi.fn<(chatId: string) => Promise<void>>();

  beforeEach(() => {
    stream.refreshTranscript.mockResolvedValue(undefined);
    refreshActiveGoal.mockReset().mockResolvedValue(undefined);
    useGoalStore.setState({ refreshActiveGoal });
    render(<ChatWindow id={OPEN_CHAT} />);
  });

  it('announces a snapshot of the open chat with the action it was taken for', () => {
    notify({ type: 'snapshot_created', chat_id: OPEN_CHAT, action: 'rollback' });

    expect(stream.toast).toHaveBeenCalledOnce();
    const [options] = stream.toast.mock.calls[0];
    expect(options).toMatchObject({ title: 'createdTitle', variant: 'default' });
    render(<>{options.description}</>);
    expect(screen.getByText('createdMessage.rollback')).toBeTruthy();
  });

  it('labels a snapshot without an action as unknown', () => {
    notify({ type: 'snapshot_created', chat_id: OPEN_CHAT });

    const [options] = stream.toast.mock.calls[0];
    render(<>{options.description}</>);
    expect(screen.getByText('createdMessage.unknown')).toBeTruthy();
  });

  it('stays quiet about snapshots of other chats and about other notification types', () => {
    notify({ type: 'snapshot_created', chat_id: 'another-chat', action: 'rollback' });
    notify({ type: 'something_else', chat_id: OPEN_CHAT });

    expect(stream.toast).not.toHaveBeenCalled();
  });

  it.each(['background_job_finish', 'voice_background_task_done'])(
    'reads the transcript again when %s finishes for the open chat',
    (kind) => {
      notify({ kind, chat_id: OPEN_CHAT });

      expect(stream.refreshTranscript).toHaveBeenCalledExactlyOnceWith(OPEN_CHAT);
    },
  );

  it('does not read the transcript for other chats or other kinds', () => {
    notify({ kind: 'background_job_finish', chat_id: 'another-chat' });
    notify({ kind: 'goal_progress', chat_id: OPEN_CHAT });

    expect(stream.refreshTranscript).not.toHaveBeenCalled();
  });

  it.each(['goal_needs_review', 'goal_usage_limit'])(
    'refreshes the active goal when %s concerns the open chat',
    (kind) => {
      notify({ kind, chat_id: OPEN_CHAT });

      expect(refreshActiveGoal).toHaveBeenCalledExactlyOnceWith(OPEN_CHAT);
    },
  );

  it('leaves the goal alone for other chats, other kinds and notifications without metadata', () => {
    notify({ kind: 'goal_needs_review', chat_id: 'another-chat' });
    notify({ kind: 'background_job_finish', chat_id: OPEN_CHAT });
    act(() => {
      window.dispatchEvent(new CustomEvent('system-notification', { detail: { data: undefined } }));
    });

    expect(refreshActiveGoal).not.toHaveBeenCalled();
  });
});
