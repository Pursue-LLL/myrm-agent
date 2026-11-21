import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api';
import { getJobDeliveryHealth } from '@/services/cron';

describe('getJobDeliveryHealth', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('asks silently about the job: the badge stays away when the verdict cannot be had, so no toast', async () => {
    vi.mocked(apiRequest).mockResolvedValue({});

    await getJobDeliveryHealth('job-1');

    expect(apiRequest).toHaveBeenCalledExactlyOnceWith('/cron/job-1/delivery-health', { silent: true });
  });

  it('hands back the verdict the server gave', async () => {
    const verdict = {
      status: 'degraded',
      failure_streak: 2,
      last_error_category: 'timeout',
      last_failed_at: '2026-06-17T08:30:00Z',
    };
    vi.mocked(apiRequest).mockResolvedValue(verdict);

    await expect(getJobDeliveryHealth('job-1')).resolves.toEqual(verdict);
  });

  // The server answers 204 when there is nothing to judge, which `apiRequest` returns as an empty object.
  it('reads the empty answer as no verdict', async () => {
    vi.mocked(apiRequest).mockResolvedValue({});

    await expect(getJobDeliveryHealth('job-1')).resolves.toBeNull();
  });
});
