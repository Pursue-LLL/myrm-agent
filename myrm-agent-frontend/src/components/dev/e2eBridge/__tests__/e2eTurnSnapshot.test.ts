/**
 * The turn snapshot of the dev bridge: what the Python E2E drivers read to decide that a turn answered.
 *
 * Real scenario: the drivers poll `turnSnapshot()` for the completion words, the counts and the streaming flag; a
 * change to how the text of the last answer is read turns a finished turn into a timeout (or a failed one into a pass)
 * without a type error. The snapshot reads the real chat store.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createSendMembers } from '@/components/dev/e2eBridge/members/send';
import type { Message } from '@/store/chat/types/messages';
import useChatStore from '@/store/useChatStore';

vi.mock('@/components/dev/e2eBridge/submitAndObserveTurn', () => ({ submitAndObserveTurn: vi.fn() }));

type Snapshot = Record<string, unknown>;

const { turnSnapshot } = createSendMembers() as unknown as { turnSnapshot: () => Snapshot };
const initialState = useChatStore.getState();

let counter = 0;
const message = (role: Message['role'], content: string): Message => ({
  messageId: `m-${counter++}`,
  chatId: 'chat-9',
  createdAt: new Date(0),
  content,
  role,
});
const show = (...messages: Message[]): Snapshot => {
  useChatStore.setState({ messages, chatId: 'chat-9' });
  return turnSnapshot();
};

beforeEach(() => {
  useChatStore.setState({ messages: [], chatId: '', loading: false, abortController: null });
});

afterEach(() => {
  useChatStore.setState(initialState, true);
});

describe('the turn snapshot', () => {
  it('reads an empty store as an empty turn', () => {
    expect(turnSnapshot()).toEqual({
      chatId: null,
      messageCount: 0,
      userCount: 0,
      assistantCount: 0,
      lastAssistantRoutingTier: null,
      lastAssistantKeys: [],
      isStreaming: false,
      hasOk: false,
      hasDone: false,
      hasCompletionSignal: false,
      lastAssistantSample: '',
      lastTwoMessages: [],
      assistantSamples: [],
      lastAssistantHasDoneSkipped: false,
      clarificationAnswered: false,
      toolApprovalQueueLen: 0,
      pendingSkillNames: [],
      pendingSkillInstruction: null,
      agentSelectedSkillCount: 0,
      slashBoundSkillResolvedCount: 0,
      slashSkillCatalogReady: true,
      marketSkillCount: 0,
    });
  });

  it('counts the messages by role and names the chat', () => {
    const snapshot = show(message('user', 'q1'), message('assistant', 'a1'), message('user', 'q2'));

    expect(snapshot).toMatchObject({ chatId: 'chat-9', messageCount: 3, userCount: 2, assistantCount: 1 });
  });

  it('reports a stream from the loading flag or from an abort controller', () => {
    expect(turnSnapshot().isStreaming).toBe(false);

    useChatStore.setState({ loading: true });
    expect(turnSnapshot().isStreaming).toBe(true);

    useChatStore.setState({ loading: false, abortController: new AbortController() });
    expect(turnSnapshot().isStreaming).toBe(true);
  });

  it.each([
    ['OK', { hasOk: true, hasDone: false, hasCompletionSignal: true, lastAssistantHasDoneSkipped: false }],
    ['ok, done', { hasOk: true, hasDone: true, hasCompletionSignal: true, lastAssistantHasDoneSkipped: false }],
    ['GOAL_OK', { hasOk: false, hasDone: false, hasCompletionSignal: true, lastAssistantHasDoneSkipped: false }],
    ['DONE-SKIPPED', { hasOk: false, hasDone: true, hasCompletionSignal: true, lastAssistantHasDoneSkipped: true }],
    ['BOOK, UNDONE', { hasOk: false, hasDone: false, hasCompletionSignal: false, lastAssistantHasDoneSkipped: false }],
  ])('finds the completion words in the last answer %j', (text, expected) => {
    expect(show(message('user', 'q'), message('assistant', text))).toMatchObject(expected);
  });

  it('reads the words from the last assistant message only', () => {
    const snapshot = show(message('assistant', 'first OK'), message('user', 'q'), message('assistant', 'second'));

    expect(snapshot).toMatchObject({ hasOk: false, lastAssistantSample: 'second', assistantCount: 2 });
  });

  it('cuts the sample of the last answer at 200 characters', () => {
    expect(show(message('assistant', 'x'.repeat(300))).lastAssistantSample).toBe('x'.repeat(200));
  });

  it('samples the last four assistant messages at 120 characters, an empty placeholder included', () => {
    const snapshot = show(
      message('assistant', 'one'),
      message('assistant', 'y'.repeat(150)),
      message('assistant', 'three'),
      message('assistant', ''),
      message('assistant', 'five'),
    );

    expect(snapshot.assistantSamples).toEqual(['y'.repeat(120), 'three', '', 'five']);
  });

  it('shapes the last two messages so that an empty sample can be traced to the store', () => {
    const snapshot = show(message('user', 'q'), message('assistant', 'z'.repeat(200)));

    expect(snapshot.lastTwoMessages).toEqual([
      {
        role: 'user',
        contentType: 'string',
        contentPreview: 'q',
        keys: ['messageId', 'chatId', 'createdAt', 'content', 'role'],
      },
      {
        role: 'assistant',
        contentType: 'string',
        contentPreview: 'z'.repeat(160),
        keys: ['messageId', 'chatId', 'createdAt', 'content', 'role'],
      },
    ]);
    expect(snapshot.lastAssistantKeys).toEqual(['messageId', 'chatId', 'createdAt', 'content', 'role']);
  });

  it('reads an assistant message without text as an empty answer', () => {
    const textless = { ...message('assistant', ''), content: undefined } as unknown as Message;
    const snapshot = show(message('user', 'q'), textless);

    expect(snapshot).toMatchObject({ hasOk: false, hasCompletionSignal: false, lastAssistantSample: '' });
    expect(snapshot.assistantSamples).toEqual(['']);
    expect(snapshot.lastTwoMessages).toMatchObject([
      { contentType: 'string' },
      { contentType: 'undefined', contentPreview: null },
    ]);
  });
});
