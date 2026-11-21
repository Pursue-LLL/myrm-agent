import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiRequest = vi.fn();
const fetchOnPageExit = vi.fn();

// A strict mock: only the two request entry points exist, since the API client alone owns the base URL.
vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
  fetchOnPageExit: (...args: unknown[]) => fetchOnPageExit(...args),
}));

// Mirrors the real builder: the agent scope is a query string appended to the finished path.
vi.mock('@/services/wikiService', () => ({
  buildWikiApiPath: (path: string, agentId?: string | null) => (agentId ? `${path}?agent_id=${agentId}` : path),
}));

import { finalizeLiveMeeting, finalizeLiveMeetingOnPageExit, ingestLiveTranscript } from '@/services/liveMeeting';

describe('liveMeeting service', () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ success: true });
    fetchOnPageExit.mockReset();
  });

  it('posts finalized transcript + line id + timestamp to the ingest endpoint without a failure toast', async () => {
    await ingestLiveTranscript('meeting-1', { id: 'line-1', text: 'hello world', timestamp: 12 });
    expect(apiRequest).toHaveBeenCalledWith('/wiki/meeting-notes/live/meeting-1/ingest', {
      method: 'POST',
      silent: true,
      body: JSON.stringify({ text: 'hello world', line_id: 'line-1', timestamp: 12 }),
    });
  });

  it('omits timestamp when not provided but always sends the line id', async () => {
    await ingestLiveTranscript('meeting-1', { id: 'line-2', text: 'hi' });
    const [, options] = apiRequest.mock.calls[0] as [string, { body: string }];
    expect(options.body).toBe(JSON.stringify({ text: 'hi', line_id: 'line-2' }));
  });

  it('finalizes the session without a failure toast and waits longer than an ordinary request for the minutes', async () => {
    await finalizeLiveMeeting('meeting-1');

    expect(apiRequest).toHaveBeenCalledExactlyOnceWith('/wiki/meeting-notes/live/meeting-1/finalize', {
      method: 'POST',
      silent: true,
      timeout: 120_000,
    });
  });

  it('finalizes on page exit without waiting for an answer, in the agent vault', () => {
    finalizeLiveMeetingOnPageExit('meeting-1', 'agent-1');

    expect(fetchOnPageExit).toHaveBeenCalledExactlyOnceWith('/wiki/meeting-notes/live/meeting-1/finalize?agent_id=agent-1', {
      method: 'POST',
    });
    expect(apiRequest).not.toHaveBeenCalled();
  });

  it('scopes ingest and finalize to the agent vault, with the scope after the action segment', async () => {
    await ingestLiveTranscript('meeting-1', { id: 'line-1', text: 'hi' }, 'agent-1');
    await finalizeLiveMeeting('meeting-1', 'agent-1');

    expect(apiRequest.mock.calls.map(([path]) => path)).toEqual([
      '/wiki/meeting-notes/live/meeting-1/ingest?agent_id=agent-1',
      '/wiki/meeting-notes/live/meeting-1/finalize?agent_id=agent-1',
    ]);
  });
});
