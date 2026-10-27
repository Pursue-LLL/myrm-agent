/**
 * processSuggestions — follow-up questions offered under a finished answer.
 * Real config and approval stores, the suggestions request is the only mocked boundary.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getSuggestions } from '@/services/chat';
import type { Message, ToolApprovalRequest } from '@/store/chat/types';
import useApprovalStore, { type ApprovalPayload } from '@/store/useApprovalStore';
import useBrowserTakeoverStore from '@/store/useBrowserTakeoverStore';
import useConfigStore from '@/store/useConfigStore';
import useDesktopControlApprovalStore from '@/store/useDesktopControlApprovalStore';
import useToolApprovalStore from '@/store/useToolApprovalStore';

import { processSuggestions } from '../messageUtils';

vi.mock('@/services/chat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/chat')>()),
  getSuggestions: vi.fn(),
}));

const CHAT_ID = 'chat-1';

const message = (overrides: Partial<Message> & Pick<Message, 'messageId' | 'role'>): Message => ({
  chatId: CHAT_ID,
  createdAt: new Date(0),
  content: '',
  ...overrides,
});

const question = message({ messageId: 'u1', role: 'user', content: 'What is Rust?' });
const answer = message({ messageId: 'a1', role: 'assistant', content: 'A systems language.' });

describe('processSuggestions', () => {
  const updateMessage = vi.fn();

  beforeEach(() => {
    vi.mocked(getSuggestions).mockReset();
    updateMessage.mockReset();
    useConfigStore.setState({ generateSearchSuggestions: true });
  });

  it('asks for follow-ups from the whole conversation and files them under the answer', async () => {
    vi.mocked(getSuggestions).mockResolvedValue(['Why Rust?', 'Rust vs Go?']);

    await processSuggestions(answer, [question, answer], updateMessage);

    expect(getSuggestions).toHaveBeenCalledWith([
      ['human', 'What is Rust?'],
      ['assistant', 'A systems language.'],
    ]);
    expect(updateMessage).toHaveBeenCalledWith('a1', ['Why Rust?', 'Rust vs Go?']);
  });

  it('does nothing when the user turned follow-ups off', async () => {
    useConfigStore.setState({ generateSearchSuggestions: false });

    await processSuggestions(answer, [question, answer], updateMessage);

    expect(getSuggestions).not.toHaveBeenCalled();
    expect(updateMessage).not.toHaveBeenCalled();
  });

  it.each([
    ['a user message', message({ messageId: 'u2', role: 'user', content: 'Hi' })],
    ['an empty answer', message({ messageId: 'a2', role: 'assistant', content: '  ' })],
    ['an answer that already has follow-ups', { ...answer, suggestions: ['Already here'] }],
  ])('does nothing for %s', async (_label, last) => {
    await processSuggestions(last, [question, last], updateMessage);

    expect(getSuggestions).not.toHaveBeenCalled();
    expect(updateMessage).not.toHaveBeenCalled();
  });

  it('skips a turn that finished in another pane (its message is not in the shown conversation)', async () => {
    const otherPaneAnswer = message({ messageId: 'a-other', role: 'assistant', content: 'Another chat.' });

    await processSuggestions(otherPaneAnswer, [question, answer], updateMessage);

    expect(getSuggestions).not.toHaveBeenCalled();
    expect(updateMessage).not.toHaveBeenCalled();
  });

  it('asks once for an answer whose follow-ups are still being generated', async () => {
    let settle: (suggestions: string[]) => void = () => undefined;
    vi.mocked(getSuggestions)
      .mockReturnValueOnce(new Promise<string[]>((resolve) => (settle = resolve)))
      .mockResolvedValue([]);

    const first = processSuggestions(answer, [question, answer], updateMessage);
    await processSuggestions(answer, [question, answer], updateMessage);
    expect(getSuggestions).toHaveBeenCalledTimes(1);

    settle(['Why Rust?']);
    await first;
    expect(updateMessage).toHaveBeenCalledTimes(1);

    // The in-flight marker is released once the request settles.
    vi.mocked(getSuggestions).mockResolvedValue(['Rust vs Go?']);
    await processSuggestions(answer, [question, answer], updateMessage);
    expect(getSuggestions).toHaveBeenCalledTimes(2);
  });

  it('lets a later turn ask again after a failed request', async () => {
    const errorLog = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.mocked(getSuggestions).mockRejectedValueOnce(new Error('upstream down')).mockResolvedValueOnce(['Why Rust?']);

    await processSuggestions(answer, [question, answer], updateMessage);
    await processSuggestions(answer, [question, answer], updateMessage);

    expect(updateMessage).toHaveBeenCalledTimes(1);
    expect(updateMessage).toHaveBeenCalledWith('a1', ['Why Rust?']);
    errorLog.mockRestore();
  });

  it('keeps the answer untouched when the request fails', async () => {
    const errorLog = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    vi.mocked(getSuggestions).mockRejectedValue(new Error('upstream down'));

    await expect(processSuggestions(answer, [question, answer], updateMessage)).resolves.toBeUndefined();

    expect(updateMessage).not.toHaveBeenCalled();
    expect(errorLog).toHaveBeenCalledWith('Failed to get suggestions:', expect.any(Error));
    errorLog.mockRestore();
  });
});

describe('processSuggestions while the turn waits for the user', () => {
  const updateMessage = vi.fn();

  const toolApproval = (messageId: string): ToolApprovalRequest => ({
    requestId: `request-${messageId}`,
    toolName: 'bash_code_execute_tool',
    toolInput: {},
    reason: 'Runs a command',
    timeoutSeconds: 300,
    expiresAt: Date.now() + 300_000,
    timeoutBehavior: 'deny',
    messageId,
    displayMode: 'approval',
    chatId: CHAT_ID,
    actionMode: 'agent',
  });
  const chatApproval = (chatId: string): ApprovalPayload => ({
    approval_id: `approval-${chatId}`,
    user_id: 'user-1',
    action_type: 'tool_call',
    status: 'pending',
    severity: 'medium',
    chat_id: chatId,
  });

  /** The decision cards the product can show; each is open for the turn that ends here ('a1') or for another one. */
  const OPEN_FOR_THIS_TURN: Array<[string, () => void]> = [
    ['a tool approval', () => useToolApprovalStore.getState().addRequest(toolApproval('a1'))],
    [
      'a desktop control approval',
      () =>
        useDesktopControlApprovalStore
          .getState()
          .requestApproval({ request_id: 'desktop-1', reason: 'Open an app', operation: 'click', messageId: 'a1' }),
    ],
    [
      'a browser takeover',
      () => useBrowserTakeoverStore.getState().requestTakeover({ reason: 'Sign in', messageId: 'a1' }),
    ],
    ['an approval of this chat', () => useApprovalStore.getState().openApproval(chatApproval(CHAT_ID))],
  ];
  const OPEN_FOR_ANOTHER_TURN: Array<[string, () => void]> = [
    ['a tool approval of another turn', () => useToolApprovalStore.getState().addRequest(toolApproval('other-turn'))],
    [
      'a desktop control approval of another turn',
      () =>
        useDesktopControlApprovalStore.getState().requestApproval({
          request_id: 'desktop-2',
          reason: 'Open an app',
          operation: 'click',
          messageId: 'other-turn',
        }),
    ],
    [
      'a browser takeover of another turn',
      () => useBrowserTakeoverStore.getState().requestTakeover({ reason: 'Sign in', messageId: 'other-turn' }),
    ],
    ['an approval of another chat', () => useApprovalStore.getState().openApproval(chatApproval('other-chat'))],
  ];

  const answered = (extra: Partial<Message> = {}): Message => ({ ...answer, ...extra });

  beforeEach(() => {
    vi.mocked(getSuggestions).mockReset();
    vi.mocked(getSuggestions).mockResolvedValue(['Why Rust?']);
    updateMessage.mockReset();
    useConfigStore.setState({ generateSearchSuggestions: true });
    useToolApprovalStore.getState().clearAll();
    useApprovalStore.getState().clearQueue();
    useDesktopControlApprovalStore.getState().clear();
    useBrowserTakeoverStore.getState().dismiss();
  });

  it.each(OPEN_FOR_THIS_TURN)('asks nothing while %s is open', async (_label, open) => {
    open();

    await processSuggestions(answer, [question, answer], updateMessage);

    expect(getSuggestions).not.toHaveBeenCalled();
    expect(updateMessage).not.toHaveBeenCalled();
  });

  it.each<[string, Partial<Message>]>([
    ['an unanswered clarification', { clarification: { answered: false } }],
    ['a plan waiting for confirmation', { planConfirmation: { plan: 'Ship it', status: 'waiting' } }],
    [
      'a human gate waiting for an answer',
      {
        humanGate: {
          question: 'Deploy?',
          options: ['Yes', 'No'],
          timeoutSeconds: 60,
          defaultAction: 'No',
          status: 'waiting',
        },
      },
    ],
  ])('asks nothing under %s', async (_label, waiting) => {
    const paused = answered(waiting);

    await processSuggestions(paused, [question, paused], updateMessage);

    expect(getSuggestions).not.toHaveBeenCalled();
    expect(updateMessage).not.toHaveBeenCalled();
  });

  it('asks again once the user has decided and the resumed turn ends', async () => {
    useToolApprovalStore.getState().addRequest(toolApproval('a1'));
    await processSuggestions(answer, [question, answer], updateMessage);
    expect(getSuggestions).not.toHaveBeenCalled();

    useToolApprovalStore.getState().removeRequest('request-a1');
    await processSuggestions(answer, [question, answer], updateMessage);

    expect(getSuggestions).toHaveBeenCalledTimes(1);
    expect(updateMessage).toHaveBeenCalledWith('a1', ['Why Rust?']);
  });

  it.each(OPEN_FOR_ANOTHER_TURN)('is not held back by %s', async (_label, open) => {
    open();

    await processSuggestions(answer, [question, answer], updateMessage);

    expect(getSuggestions).toHaveBeenCalledTimes(1);
  });

  it.each<[string, Partial<Message>]>([
    ['an answered clarification', { clarification: { answered: true } }],
    ['a confirmed plan', { planConfirmation: { plan: 'Ship it', status: 'confirmed' } }],
    [
      'a resolved human gate',
      {
        humanGate: {
          question: 'Deploy?',
          options: ['Yes'],
          timeoutSeconds: 60,
          defaultAction: 'Yes',
          status: 'resolved',
        },
      },
    ],
  ])('is not held back by %s', async (_label, settled) => {
    const done = answered(settled);

    await processSuggestions(done, [question, done], updateMessage);

    expect(getSuggestions).toHaveBeenCalledTimes(1);
  });

  it('asks once when two turn ends race through the waiting check', async () => {
    await Promise.all([
      processSuggestions(answer, [question, answer], updateMessage),
      processSuggestions(answer, [question, answer], updateMessage),
    ]);

    expect(getSuggestions).toHaveBeenCalledTimes(1);
  });

  it('still asks when the waiting check itself cannot be evaluated', async () => {
    const warnLog = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const unavailable = vi.spyOn(useApprovalStore, 'getState').mockImplementation(() => {
      throw new Error('approval store unavailable');
    });

    try {
      await expect(processSuggestions(answer, [question, answer], updateMessage)).resolves.toBeUndefined();
    } finally {
      unavailable.mockRestore();
      warnLog.mockRestore();
    }

    expect(getSuggestions).toHaveBeenCalledTimes(1);
    expect(updateMessage).toHaveBeenCalledWith('a1', ['Why Rust?']);
  });
});
