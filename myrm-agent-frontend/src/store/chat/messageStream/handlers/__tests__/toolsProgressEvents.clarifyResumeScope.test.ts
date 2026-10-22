/**
 * The clarify card's resume/legacy decision describes the turn that raised it, not the chat on screen.
 *
 * Real scenario: chat A (a plain agent turn) pauses on a clarification while the user reads chat B, which is in
 * deep-research mode. A's card must stay on the resume path; reading B's mode would send the answer down the
 * deep-research-only legacy route and the card could not be answered.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/notification', () => ({
  notificationService: { notify: vi.fn() },
}));

vi.mock('@/lib/approval/buildToolApprovalRequest', () => ({
  buildToolApprovalRequest: vi.fn(() => ({ id: 'mock-req' })),
}));

vi.mock('@/lib/approval/approvalAlertService', () => ({
  notifyIdleApproval: vi.fn(),
}));

import useChatStore from '@/store/useChatStore';
import type { StreamHandlerState } from '../../types';
import { toolsProgressEvents } from '../toolsProgressEvents';
import type { StreamCtx } from '../../streamContext';

const OPEN_CHAT = 'chat-open';

/** A plain agent clarification: no `source`, as the harness sends for a general agent turn. */
function clarifyCtx(streamChatId: string): StreamCtx {
  const state = {
    chatId: streamChatId,
    messages: [],
    messageAppeared: false,
    loading: true,
    scheduler: {} as StreamHandlerState['scheduler'],
  } as unknown as StreamHandlerState;
  return {
    data: {
      type: 'clarification_required',
      messageId: 'msg-1',
      data: { type: 'ask_question', form: { title: 'Which one?', questions: [{ id: 'q1', prompt: 'Pick' }] } },
    } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state,
    actions: {
      setLoading: vi.fn(),
      setMessageAppeared: vi.fn(),
      setMessages: vi.fn(),
    } as never,
    files: [],
  };
}

function isResumeModeOf(ctx: StreamCtx): boolean | undefined {
  let last: { messages: Array<{ clarification?: { isResumeMode?: boolean } }> } | undefined;
  const calls = (ctx.actions.setMessages as unknown as ReturnType<typeof vi.fn>).mock.calls as Array<
    [(s: Record<string, unknown>) => void]
  >;
  for (const [fn] of calls) {
    const draft: Record<string, unknown> = {
      messages: [
        { messageId: 'msg-1', chatId: ctx.state.chatId, role: 'assistant', content: '', createdAt: new Date() },
      ],
    };
    fn(draft);
    last = draft as typeof last;
  }
  return last?.messages[0]?.clarification?.isResumeMode;
}

describe('toolsProgressEvents clarify resume scope', () => {
  beforeEach(() => {
    // The user is sitting in a deep-research chat; a background agent turn raises the clarification.
    useChatStore.setState({ chatId: OPEN_CHAT, actionMode: 'deep_research' });
  });

  it('keeps a general-agent clarification on the resume path when the open chat is in deep research', async () => {
    const ctx = clarifyCtx('chat-background');
    await toolsProgressEvents(ctx);
    await vi.dynamicImportSettled();

    expect(isResumeModeOf(ctx)).toBe(true);
  });
});
