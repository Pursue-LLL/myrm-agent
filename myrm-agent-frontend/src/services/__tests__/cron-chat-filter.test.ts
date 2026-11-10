import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api';
import { countChatCronJobs, listCronJobs } from '@/services/cron';

describe('listCronJobs chat_id filter', () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 50, has_more: false });
  });

  it('passes chat_id query param to the API', async () => {
    await listCronJobs({ chat_id: 'chat-123' });
    expect(apiRequest).toHaveBeenCalledWith('/cron?chat_id=chat-123');
  });
});

describe('countChatCronJobs', () => {
  it('reads only the total of the chat, without raising an error toast of its own', async () => {
    vi.mocked(apiRequest).mockResolvedValue({ items: [], total: 7, offset: 0, limit: 1, has_more: true });

    await expect(countChatCronJobs('chat/1&x')).resolves.toBe(7);

    expect(apiRequest).toHaveBeenLastCalledWith('/cron?chat_id=chat%2F1%26x&limit=1', { silent: true });
  });

  it('lets a failed read reach the caller', async () => {
    vi.mocked(apiRequest).mockRejectedValue(new Error('offline'));

    await expect(countChatCronJobs('chat-1')).rejects.toThrow('offline');
  });
});
