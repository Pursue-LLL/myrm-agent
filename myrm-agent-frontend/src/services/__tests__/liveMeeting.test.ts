import { beforeEach, describe, expect, it, vi } from 'vitest';

const apiRequest = vi.fn();

vi.mock('@/lib/api', () => ({
  apiRequest: (...args: unknown[]) => apiRequest(...args),
  getApiUrl: (endpoint: string) => `http://test/api/v1${endpoint}`,
}));

vi.mock('@/services/wikiService', () => ({
  buildWikiApiPath: (path: string) => path,
}));

import {
  finalizeLiveMeeting,
  getLiveMeetingSnapshot,
  ingestLiveTranscript,
} from '@/services/liveMeeting';

describe('liveMeeting service', () => {
  beforeEach(() => {
    apiRequest.mockReset();
    apiRequest.mockResolvedValue({ success: true });
  });

  it('posts finalized transcript + timestamp to the ingest endpoint', async () => {
    await ingestLiveTranscript('meeting-1', 'hello world', 12);
    expect(apiRequest).toHaveBeenCalledWith(
      'http://test/api/v1/wiki/meeting-notes/live/meeting-1/ingest',
      { method: 'POST', body: JSON.stringify({ text: 'hello world', timestamp: 12 }) },
    );
  });

  it('omits timestamp when not provided', async () => {
    await ingestLiveTranscript('meeting-1', 'hi');
    const [, options] = apiRequest.mock.calls[0] as [string, { body: string }];
    expect(options.body).toBe(JSON.stringify({ text: 'hi' }));
  });

  it('reads the snapshot and finalizes the session', async () => {
    await getLiveMeetingSnapshot('meeting-1');
    expect(apiRequest).toHaveBeenCalledWith(
      'http://test/api/v1/wiki/meeting-notes/live/meeting-1',
      { method: 'GET' },
    );

    await finalizeLiveMeeting('meeting-1');
    expect(apiRequest).toHaveBeenCalledWith(
      'http://test/api/v1/wiki/meeting-notes/live/meeting-1/finalize',
      { method: 'POST', body: JSON.stringify({}) },
    );
  });
});
