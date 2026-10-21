/**
 * processSuggestions — follow-up questions offered under a finished answer.
 * Real config store, the suggestions request is the only mocked boundary.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { getSuggestions } from '@/services/chat';
import type { Message } from '@/store/chat/types';
import useConfigStore from '@/store/useConfigStore';

import { processSuggestions } from '../messageUtils';

vi.mock('@/services/chat', () => ({ getSuggestions: vi.fn() }));

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
