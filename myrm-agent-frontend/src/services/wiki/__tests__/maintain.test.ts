import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as api from '@/lib/api';
import { LONG_RUNNING_REQUEST_TIMEOUT_MS } from '@/lib/constants/requestTimeouts';
import { wikiService } from '../service';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
  getApiUrl: vi.fn((path: string) => path),
  fetchWithTimeout: vi.fn(),
}));

describe('wikiService.maintainWiki', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('outlasts the default 30s request timeout (full mode runs one LLM call per page)', async () => {
    vi.mocked(api.apiRequest).mockResolvedValueOnce({ issues_found: 0 });

    await wikiService.maintainWiki('full', 'agent_dev');

    expect(api.apiRequest).toHaveBeenCalledWith(
      '/wiki/maintain?mode=full&agent_id=agent_dev',
      expect.objectContaining({ method: 'POST', timeout: LONG_RUNNING_REQUEST_TIMEOUT_MS }),
    );
    expect(LONG_RUNNING_REQUEST_TIMEOUT_MS).toBeGreaterThan(10 * 60 * 1000);
  });

  it('applies the same long timeout to structural mode', async () => {
    vi.mocked(api.apiRequest).mockResolvedValueOnce({ issues_found: 0 });

    await wikiService.maintainWiki('structural');

    expect(api.apiRequest).toHaveBeenCalledWith(
      '/wiki/maintain?mode=structural',
      expect.objectContaining({ timeout: LONG_RUNNING_REQUEST_TIMEOUT_MS }),
    );
  });
});
