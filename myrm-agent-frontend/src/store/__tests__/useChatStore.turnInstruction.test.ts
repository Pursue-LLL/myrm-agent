/** @vitest-environment jsdom */
/**
 * steerMessage / redirectMessage report whether the running turn took the instruction.
 *
 * Real scenario: the user presses "redirect" while the turn is still starting or has just ended. The backend refuses
 * with HTTP 200 and a `success: false` envelope rather than an HTTP error status, so the status alone says nothing -
 * a caller that reads it as an acceptance never queues the instruction and silently loses it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';
import { fetchWithTimeout } from '@/lib/api';

vi.mock('@/lib/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/api')>()),
  fetchWithTimeout: vi.fn(),
}));

vi.mock('@/lib/mobileRemote', () => ({
  isMobileRemoteSurface: vi.fn(() => false),
  mobileRemotePost: vi.fn(),
}));

/** The body the backend answers for a chat that has no running turn (HTTP 200). */
const NO_RUNNING_TURN = { success: false, code: 404, message: 'No active agent for this chat', error: null };
const ACCEPTED = { success: true, code: 0, data: { steered: true, chat_id: 'chat-1' } };

const mockFetch = vi.mocked(fetchWithTimeout);

function answer(body: unknown, status = 200): void {
  mockFetch.mockResolvedValueOnce({ ok: status >= 200 && status < 300, status, json: async () => body } as Response);
}

beforeEach(() => {
  mockFetch.mockReset();
  useChatStore.setState({ chatId: 'chat-1' });
});

describe.each([
  ['steerMessage', 'steer'],
  ['redirectMessage', 'redirect'],
] as const)('%s', (action, endpoint) => {
  const send = (message: string) => useChatStore.getState()[action](message);

  it('resolves true when the running turn took the instruction', async () => {
    answer(ACCEPTED);

    expect(await send('go left')).toBe(true);
    expect(mockFetch).toHaveBeenCalledTimes(1);
  });

  it('resolves false when the backend answers 200 with a refusal envelope', async () => {
    answer(NO_RUNNING_TURN);

    expect(await send('go left')).toBe(false);
  });

  it('resolves false on an HTTP error status', async () => {
    answer({ detail: 'Too Many Requests' }, 429);

    expect(await send('go left')).toBe(false);
  });

  it('resolves false when the request itself fails', async () => {
    mockFetch.mockRejectedValueOnce(new Error('network down'));

    expect(await send('go left')).toBe(false);
  });

  it('posts the instruction to the chat endpoint', async () => {
    answer(ACCEPTED);

    await send('go left');

    expect(mockFetch).toHaveBeenCalledWith(
      `/agents/chats/chat-1/${endpoint}`,
      expect.objectContaining({
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: expect.stringContaining('"message":"go left"'),
      }),
    );
  });

  it('sends nothing without an open chat', async () => {
    useChatStore.setState({ chatId: undefined });

    expect(await send('go left')).toBe(false);
    expect(mockFetch).not.toHaveBeenCalled();
  });
});

describe('steerMessage options', () => {
  it('passes the reply context of an async agent question to the backend', async () => {
    answer(ACCEPTED);

    await useChatStore.getState().steerMessage('use pnpm', {
      mode: 'policy',
      quotedRef: 'artifact-1',
      inReplyToCallId: 'call-7',
      questionContext: 'Which package manager?',
    });

    const [, init] = mockFetch.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({
      message: 'use pnpm',
      mode: 'policy',
      quotedRef: 'artifact-1',
      in_reply_to_call_id: 'call-7',
      question_context: 'Which package manager?',
    });
  });

  it('omits the options that were not given', async () => {
    answer(ACCEPTED);

    await useChatStore.getState().steerMessage('use pnpm');

    const [, init] = mockFetch.mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({ message: 'use pnpm' });
  });
});
