import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api';
import { triggerCronJob } from '@/services/cron';

describe('triggerCronJob', () => {
  it('posts silently: the page tells "already running" (409) from a failure, so a global toast would double it', async () => {
    vi.mocked(apiRequest).mockResolvedValue({ triggered: true });

    await triggerCronJob('job-1');

    expect(apiRequest).toHaveBeenCalledWith('/cron/job-1/trigger', { method: 'POST', silent: true });
  });
});
