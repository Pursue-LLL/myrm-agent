import { beforeEach, describe, expect, it, vi } from 'vitest';

import * as api from '@/lib/api';
import { LONG_RUNNING_REQUEST_TIMEOUT_MS } from '@/lib/constants/requestTimeouts';
import { cancelWikiMaintain, getWikiMaintainStatus, startWikiMaintain } from '../maintain';
import { wikiService } from '../service';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
  getApiUrl: vi.fn((path: string) => path),
  fetchWithTimeout: vi.fn(),
}));

const IDLE_STATUS = {
  state: 'idle',
  mode: null,
  phase: null,
  done: 0,
  total: 0,
  cancel_requested: false,
  result: null,
  error_code: null,
};

describe('wiki maintenance run client', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('starts a run with a plain POST: the server answers at once and the run continues in the background', async () => {
    vi.mocked(api.apiRequest).mockResolvedValueOnce({ ...IDLE_STATUS, state: 'running', mode: 'full' });

    const status = await startWikiMaintain('full', 'agent_dev');

    expect(api.apiRequest).toHaveBeenCalledWith('/wiki/maintain?mode=full&agent_id=agent_dev', { method: 'POST' });
    expect(status.state).toBe('running');
  });

  it('starts a structural run without an agent scope', async () => {
    vi.mocked(api.apiRequest).mockResolvedValueOnce({ ...IDLE_STATUS, state: 'running', mode: 'structural' });

    await startWikiMaintain('structural');

    expect(api.apiRequest).toHaveBeenCalledWith('/wiki/maintain?mode=structural', { method: 'POST' });
  });

  it('reads the run status of the agent scope', async () => {
    vi.mocked(api.apiRequest).mockResolvedValueOnce(IDLE_STATUS);

    await getWikiMaintainStatus('agent_dev');

    expect(api.apiRequest).toHaveBeenCalledWith('/wiki/maintain/status?agent_id=agent_dev');
  });

  it('reads the default scope status without a query', async () => {
    vi.mocked(api.apiRequest).mockResolvedValueOnce(IDLE_STATUS);

    await getWikiMaintainStatus();

    expect(api.apiRequest).toHaveBeenCalledWith('/wiki/maintain/status');
  });

  it('asks the run of the agent scope to stop with a plain POST and returns its status', async () => {
    vi.mocked(api.apiRequest).mockResolvedValueOnce({
      ...IDLE_STATUS,
      state: 'running',
      mode: 'full',
      cancel_requested: true,
    });

    const status = await cancelWikiMaintain('agent_dev');

    expect(api.apiRequest).toHaveBeenCalledWith('/wiki/maintain/cancel?agent_id=agent_dev', { method: 'POST' });
    expect(status.cancel_requested).toBe(true);
  });

  it('cancels the default scope without a query', async () => {
    vi.mocked(api.apiRequest).mockResolvedValueOnce(IDLE_STATUS);

    await cancelWikiMaintain();

    expect(api.apiRequest).toHaveBeenCalledWith('/wiki/maintain/cancel', { method: 'POST' });
  });
});

describe('wikiService.compileWiki', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('outlasts the default 30s request timeout: compile runs sequential model stages and answers when done', async () => {
    vi.mocked(api.apiRequest).mockResolvedValueOnce({ concepts_count: 0 });

    await wikiService.compileWiki('agent_dev');

    expect(api.apiRequest).toHaveBeenCalledWith(
      '/wiki/compile?agent_id=agent_dev',
      expect.objectContaining({ method: 'POST', timeout: LONG_RUNNING_REQUEST_TIMEOUT_MS }),
    );
    expect(LONG_RUNNING_REQUEST_TIMEOUT_MS).toBeGreaterThan(10 * 60 * 1000);
  });
});
