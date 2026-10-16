import { describe, it, expect, vi, beforeEach } from 'vitest';
import { apiRequest } from '@/lib/api';
import { systemService } from '../system';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

const DEFAULT_REQUEST_TIMEOUT_MS = 30_000;

describe('systemService.getStorageGovernanceReport', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(apiRequest).mockResolvedValue({});
  });

  it('waits longer than the default request budget because measuring walks every file of the instance', async () => {
    await systemService.getStorageGovernanceReport();

    const [, options] = vi.mocked(apiRequest).mock.calls[0];
    expect(options?.timeout).toBeGreaterThan(DEFAULT_REQUEST_TIMEOUT_MS);
  });

  it('stays silent so the card, not a global toast, reports a failed measurement', async () => {
    await systemService.getStorageGovernanceReport();

    const [, options] = vi.mocked(apiRequest).mock.calls[0];
    expect(options?.silent).toBe(true);
  });

  it('asks the governance endpoint for a fresh report', async () => {
    await systemService.getStorageGovernanceReport();

    const [endpoint] = vi.mocked(apiRequest).mock.calls[0];
    expect(endpoint).toMatch(/^\/system\/storage\/governance\?t=\d+$/);
  });
});
