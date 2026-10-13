import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '@/lib/api';
import { rewindToMessage } from '@/services/chat';

vi.mock('@/lib/api', () => ({
  API_BASE_URL: '',
  apiRequest: vi.fn(),
  fetchWithTimeout: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('rewindToMessage', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('asks the server to rewind to the message and leaves reporting a failure to its caller', async () => {
    apiRequestMock.mockResolvedValue({ success: true, deleted_count: 3 });

    const result = await rewindToMessage('chat-1', 'm-2', 'both');

    expect(result).toEqual({ success: true, deleted_count: 3 });
    // RewindDialog tells the user once itself; a request-level toast would report the same failure twice.
    expect(apiRequestMock).toHaveBeenCalledWith('/chats/chat-1/rewind', {
      method: 'POST',
      body: JSON.stringify({ message_id: 'm-2', scope: 'both' }),
      silent: true,
    });
  });

  it('rewinds the conversation only when no scope is given', async () => {
    apiRequestMock.mockResolvedValue({ success: true });

    await rewindToMessage('chat-1', 'm-2');

    expect(apiRequestMock).toHaveBeenCalledWith(
      '/chats/chat-1/rewind',
      expect.objectContaining({ body: JSON.stringify({ message_id: 'm-2', scope: 'conversation' }) }),
    );
  });
});
