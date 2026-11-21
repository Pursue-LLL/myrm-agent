/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// The readiness probe would poll a backend that does not exist here; the request itself is what is under test.
vi.mock('@/lib/backend-health', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/backend-health')>()),
  ensureLocalBackendReady: async () => true,
}));

import { getApiUrl } from '@/lib/api';
import { finalizeLiveMeeting, finalizeLiveMeetingOnPageExit, ingestLiveTranscript } from '@/services/liveMeeting';

const fetchSpy = vi.fn();

beforeEach(() => {
  fetchSpy.mockReset();
  fetchSpy.mockImplementation(
    async () =>
      new Response(JSON.stringify({ success: true }), { status: 200, headers: { 'content-type': 'application/json' } }),
  );
  vi.stubGlobal('fetch', fetchSpy);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('liveMeeting requests on the wire', () => {
  it.each([
    ['ingest', () => ingestLiveTranscript('meeting 1', { id: 'line-1', text: 'hi' }), '/ingest'],
    ['finalize', () => finalizeLiveMeeting('meeting 1'), '/finalize'],
  ])('sends the %s request to the API base URL exactly once', async (_name, call, suffix) => {
    await call();

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe(getApiUrl(`/wiki/meeting-notes/live/meeting%201${suffix}`));
    expect(init).toMatchObject({ method: 'POST' });
  });

  it('sends the page-exit finalize as a keepalive request, in the agent scope, before the page can go away', () => {
    finalizeLiveMeetingOnPageExit('meeting 1', 'agent 1');

    expect(fetchSpy).toHaveBeenCalledOnce();
    const [url, init] = fetchSpy.mock.calls[0];
    expect(url).toBe(getApiUrl('/wiki/meeting-notes/live/meeting%201/finalize?agent_id=agent%201'));
    expect(init).toMatchObject({ method: 'POST', keepalive: true });
  });

  it.each([
    ['ingest', () => ingestLiveTranscript('meeting 1', { id: 'line-1', text: 'hi' }, 'agent 1'), '/ingest'],
    ['finalize', () => finalizeLiveMeeting('meeting 1', 'agent 1'), '/finalize'],
  ])('puts the agent scope of the %s request in the query, after the action segment', async (_name, call, suffix) => {
    await call();

    expect(fetchSpy).toHaveBeenCalledOnce();
    expect(fetchSpy.mock.calls[0][0]).toBe(
      getApiUrl(`/wiki/meeting-notes/live/meeting%201${suffix}?agent_id=agent%201`),
    );
  });
});
