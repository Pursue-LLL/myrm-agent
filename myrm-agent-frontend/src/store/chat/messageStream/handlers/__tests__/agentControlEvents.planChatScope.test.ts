/**
 * The plan panel and the open chat describe the chat the user has open.
 *
 * Real scenario: a goal turn runs in chat A while the user reads chat B. A's terminal event (ERROR / AGENT_CANCELLED)
 * must not wipe the plan B is showing, and A's context overflow must not reset B's conversation.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/utils/toast', () => ({
  toast: { error: vi.fn(), warning: vi.fn() },
}));

vi.mock('@/lib/inspector/releaseTurnInspectorControls', () => ({
  releaseTurnInspectorControls: vi.fn(() => Promise.resolve()),
}));

import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import useChatStore from '@/store/useChatStore';
import type { StreamHandlerState } from '../../types';
import { agentControlEvents } from '../agentControlEvents';
import type { StreamCtx } from '../../streamContext';

const OPEN_CHAT = 'chat-open';
const BACKGROUND_CHAT = 'chat-background';

function makeActivePlan() {
  return {
    goal: 'Plan of the open chat',
    reasoning: '',
    steps: [
      { step_id: 'a', description: 'Step A', expected_output: '', status: 'in_progress' as const, dependencies: [] },
      { step_id: 'b', description: 'Step B', expected_output: '', status: 'pending' as const, dependencies: [] },
    ],
  };
}

/** The stream of `streamChatId`, delivering the terminal `data`. */
function streamOf(streamChatId: string, data: Record<string, unknown>): StreamCtx {
  const state: StreamHandlerState = {
    chatId: streamChatId,
    messages: [{ messageId: 'msg-1', chatId: streamChatId, role: 'assistant', content: '', createdAt: new Date() }],
    messageAppeared: false,
    loading: true,
    scheduler: {} as StreamHandlerState['scheduler'],
  };
  return {
    data: { messageId: 'msg-1', ...data } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state,
    actions: {
      setMessages: vi.fn((updater: (s: Record<string, unknown>) => void) =>
        updater({
          messages: [
            { messageId: 'msg-1', chatId: streamChatId, role: 'assistant', content: '', createdAt: new Date() },
          ],
          loading: true,
          messageAppeared: false,
        }),
      ),
      setLoading: vi.fn(),
      setMessageAppeared: vi.fn(),
      _processSuggestions: vi.fn(async () => undefined),
      scheduleAutoSave: vi.fn(),
    } as never,
    files: [],
  };
}

const terminalEvents = [
  ['error', { type: 'error', error: 'Task failed' }],
  ['agent_cancelled', { type: 'agent_cancelled', data: { reason: 'user_cancelled' } }],
] as const;

describe('agentControlEvents plan scope', () => {
  beforeEach(() => {
    usePlanStore.setState({ plan: makeActivePlan(), isLoading: false });
    useChatStore.setState({ chatId: OPEN_CHAT });
  });

  it.each(terminalEvents)('clears the plan when the open chat ends with %s', async (_name, data) => {
    await agentControlEvents(streamOf(OPEN_CHAT, data));
    await vi.dynamicImportSettled();

    expect(usePlanStore.getState().plan).toBeNull();
  });

  it.each(terminalEvents)(
    'leaves the plan of the open chat alone when a background chat ends with %s',
    async (_name, data) => {
      await agentControlEvents(streamOf(BACKGROUND_CHAT, data));
      await vi.dynamicImportSettled();

      expect(usePlanStore.getState().plan?.goal).toBe('Plan of the open chat');
    },
  );
});

describe('agentControlEvents context overflow reset scope', () => {
  const initializeChat = vi.fn<(id?: string, options?: { forceReload?: boolean }) => void>();

  beforeEach(() => {
    initializeChat.mockClear();
    usePlanStore.setState({ plan: makeActivePlan(), isLoading: false });
    useChatStore.setState({ chatId: OPEN_CHAT, initializeChat });
  });

  it('resets the conversation when the open chat overflows its context', async () => {
    await agentControlEvents(streamOf(OPEN_CHAT, { type: 'context_overflow_reset', data: { chat_id: OPEN_CHAT } }));
    await vi.dynamicImportSettled();

    expect(initializeChat).toHaveBeenCalledTimes(1);
  });

  it('leaves the open chat alone when a background chat overflows its context', async () => {
    await agentControlEvents(
      streamOf(BACKGROUND_CHAT, { type: 'context_overflow_reset', data: { chat_id: BACKGROUND_CHAT } }),
    );
    await vi.dynamicImportSettled();

    expect(initializeChat).not.toHaveBeenCalled();
  });
});
