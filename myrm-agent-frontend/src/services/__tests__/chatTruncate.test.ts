import { beforeEach, describe, expect, it, vi } from 'vitest';
import { apiRequest } from '@/lib/api';
import { truncateAfterMessage } from '@/services/chat';

vi.mock('@/lib/api', () => ({
  API_BASE_URL: '',
  apiRequest: vi.fn(),
  fetchWithTimeout: vi.fn(),
}));

const apiRequestMock = vi.mocked(apiRequest);

describe('truncateAfterMessage', () => {
  beforeEach(() => {
    apiRequestMock.mockReset();
  });

  it('asks the server to cut at the message and leaves reporting a failure to its caller', async () => {
    apiRequestMock.mockResolvedValue({ success: true, deleted_count: 2 });

    const result = await truncateAfterMessage('chat-1', 'm-2');

    expect(result).toEqual({ success: true, deleted_count: 2 });
    // The edit flow tells the user once itself; a request-level toast would report the same failure twice.
    expect(apiRequestMock).toHaveBeenCalledWith('/chats/chat-1/truncate-after', {
      method: 'POST',
      body: JSON.stringify({ message_id: 'm-2' }),
      silent: true,
    });
  });
});
