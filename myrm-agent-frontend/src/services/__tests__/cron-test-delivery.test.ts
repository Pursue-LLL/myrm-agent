import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api';
import { testCronDelivery } from '@/services/cron';

describe('testCronDelivery', () => {
  it('POSTs without body when no config override is given', async () => {
    vi.mocked(apiRequest).mockResolvedValue({ delivered: true });
    await testCronDelivery('job-1');
    expect(apiRequest).toHaveBeenCalledWith('/cron/job-1/test-delivery', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
      timeout: 60000,
    });
  });

  it('POSTs a delivery override', async () => {
    vi.mocked(apiRequest).mockResolvedValue({ delivered: true });
    await testCronDelivery('job-1', { delivery: { channel: 'webhook', target: 'https://x.example.com/h' } });
    expect(apiRequest).toHaveBeenCalledWith('/cron/job-1/test-delivery', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ delivery: { channel: 'webhook', target: 'https://x.example.com/h' } }),
      timeout: 60000,
    });
  });

  it('POSTs a failure_delivery override', async () => {
    vi.mocked(apiRequest).mockResolvedValue({ delivered: true });
    await testCronDelivery('job-1', {
      failure_delivery: { channel: 'webhook', target: 'https://alerts.example.com/f' },
    });
    expect(apiRequest).toHaveBeenCalledWith('/cron/job-1/test-delivery', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        failure_delivery: { channel: 'webhook', target: 'https://alerts.example.com/f' },
      }),
      timeout: 60000,
    });
  });
});
