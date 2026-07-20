import { describe, expect, it, vi, beforeEach } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api';
import { listCronJobs } from '@/services/cron';

describe('listCronJobs chat_id filter', () => {
  beforeEach(() => {
    vi.mocked(apiRequest).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 50, has_more: false });
  });

  it('passes chat_id query param to the API', async () => {
    await listCronJobs({ chat_id: 'chat-123' });
    expect(apiRequest).toHaveBeenCalledWith('/cron?chat_id=chat-123');
  });
});
