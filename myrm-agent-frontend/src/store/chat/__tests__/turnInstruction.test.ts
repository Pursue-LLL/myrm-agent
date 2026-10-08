/**
 * postTurnInstruction decides from the backend envelope whether the running turn took a steer / redirect instruction.
 *
 * The bodies below are the shapes the backend really answers with: a refusal is HTTP 200 + `success: false`
 * (`error_response`), an acceptance is HTTP 200 + `success: true` (`success_response`).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchWithTimeout } from '@/lib/api';
import { isMobileRemoteSurface, mobileRemotePost } from '@/lib/mobileRemote';
import { postTurnInstruction } from '../turnInstruction';

vi.mock('@/lib/api', () => ({ fetchWithTimeout: vi.fn() }));
vi.mock('@/lib/mobileRemote', () => ({ isMobileRemoteSurface: vi.fn(), mobileRemotePost: vi.fn() }));

const mockFetch = vi.mocked(fetchWithTimeout);
const mockMobilePost = vi.mocked(mobileRemotePost);
const mockIsMobile = vi.mocked(isMobileRemoteSurface);

const NO_RUNNING_TURN = { success: false, code: 404, message: 'No active agent for this chat', error: null };
const TOO_LARGE = {
  success: false,
  code: 400,
  message: 'Steering message too large; reference artifacts instead',
  error: null,
};
const TAKEN = { success: true, code: 0, data: { steered: true, chat_id: 'chat-1' } };
const TAKEN_AGAIN = { success: true, code: 0, data: { steered: true, chat_id: 'chat-1', deduped: true } };

function reply(body: unknown, status = 200): void {
  mockFetch.mockResolvedValueOnce({ ok: status >= 200 && status < 300, status, json: async () => body } as Response);
}

beforeEach(() => {
  vi.resetAllMocks();
  mockIsMobile.mockReturnValue(false);
});

describe('on the direct connection', () => {
  it('takes the instruction when the backend confirms it', async () => {
    reply(TAKEN);

    expect(await postTurnInstruction('chat-1', 'steer', { message: 'go left' })).toBe(true);
  });

  it('takes a repeated instruction the backend has already applied', async () => {
    reply(TAKEN_AGAIN);

    expect(await postTurnInstruction('chat-1', 'steer', { message: 'go left' })).toBe(true);
  });

  it.each([
    ['no turn is running', NO_RUNNING_TURN],
    ['the message is refused as too large', TOO_LARGE],
  ])('keeps the instruction when %s, although the HTTP status is 200', async (_label, body) => {
    reply(body);

    expect(await postTurnInstruction('chat-1', 'redirect', { message: 'go left' })).toBe(false);
  });

  it('keeps the instruction on an HTTP error status', async () => {
    reply({ detail: 'Internal Server Error' }, 500);

    expect(await postTurnInstruction('chat-1', 'steer', { message: 'go left' })).toBe(false);
  });

  it('keeps the instruction when the reply is not a readable body, e.g. a proxy page answering 200', async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => {
        throw new SyntaxError('Unexpected token < in JSON');
      },
    } as unknown as Response);

    expect(await postTurnInstruction('chat-1', 'steer', { message: 'go left' })).toBe(false);
  });

  it('keeps the instruction when the request fails', async () => {
    mockFetch.mockRejectedValueOnce(new TypeError('Failed to fetch'));

    expect(await postTurnInstruction('chat-1', 'steer', { message: 'go left' })).toBe(false);
  });

  it('posts the payload as JSON to the endpoint of the chosen kind', async () => {
    reply(TAKEN);

    await postTurnInstruction('chat-1', 'redirect', { message: 'go left' });

    expect(mockFetch).toHaveBeenCalledWith('/agents/chats/chat-1/redirect', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'go left' }),
    });
    expect(mockMobilePost).not.toHaveBeenCalled();
  });
});

describe('on the mobile remote surface', () => {
  beforeEach(() => {
    mockIsMobile.mockReturnValue(true);
  });

  it('takes the instruction when the channel hands back the confirmation payload', async () => {
    mockMobilePost.mockResolvedValueOnce({ steered: true, chat_id: 'chat-1' });

    expect(await postTurnInstruction('chat-1', 'steer', { message: 'go left' })).toBe(true);
  });

  it('keeps the instruction when the channel hands back a refusal envelope', async () => {
    mockMobilePost.mockResolvedValueOnce(NO_RUNNING_TURN);

    expect(await postTurnInstruction('chat-1', 'steer', { message: 'go left' })).toBe(false);
  });

  it('keeps the instruction when the channel rejects', async () => {
    mockMobilePost.mockRejectedValueOnce(new Error('Mobile API failed: 403'));

    expect(await postTurnInstruction('chat-1', 'redirect', { message: 'go left' })).toBe(false);
  });

  it('posts the payload to the versioned endpoint of the chosen kind', async () => {
    mockMobilePost.mockResolvedValueOnce({ redirected: true });

    await postTurnInstruction('chat-1', 'redirect', { message: 'go left' });

    expect(mockMobilePost).toHaveBeenCalledWith('/api/v1/agents/chats/chat-1/redirect', { message: 'go left' });
    expect(mockFetch).not.toHaveBeenCalled();
  });
});
