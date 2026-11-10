import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/api', () => ({
  apiRequest: vi.fn(),
}));

import { apiRequest } from '@/lib/api';
import { getPreferenceRadarState, tunePreferenceRadar } from '@/services/memory/preferences';

const serverState = {
  session_id: 'chat-1',
  recency: 1.5,
  actionability: 1,
  technical_depth: 1,
  conciseness: 1,
  breadth: 1,
  locked: true,
  last_updated: '2026-03-15T12:00:00Z',
  effective_signal_weights: { recency: 1.5 },
};

beforeEach(() => {
  vi.mocked(apiRequest).mockReset();
  vi.mocked(apiRequest).mockResolvedValue(serverState);
});

describe('getPreferenceRadarState', () => {
  it('reads the session without raising an error notice of its own and returns the flat state', async () => {
    const state = await getPreferenceRadarState('chat-1');

    expect(apiRequest).toHaveBeenCalledExactlyOnceWith('/memory/radar/chat-1', { silent: true });
    expect(state).toBe(serverState);
  });

  it('escapes the session id in the path', async () => {
    await getPreferenceRadarState('a/b c');

    expect(vi.mocked(apiRequest).mock.calls[0][0]).toBe('/memory/radar/a%2Fb%20c');
  });
});

describe('tunePreferenceRadar', () => {
  it.each([
    ['one weight', { breadth: 2.5 }, '{"breadth":2.5}'],
    ['the lock flag', { locked: true }, '{"locked":true}'],
    ['a reset', { reset_to_neutral: true }, '{"reset_to_neutral":true}'],
  ])('posts %s as flat fields next to the session', async (_name, request, expectedBody) => {
    const state = await tunePreferenceRadar('chat-1', request);

    expect(apiRequest).toHaveBeenCalledExactlyOnceWith('/memory/radar/chat-1/tune', {
      method: 'POST',
      body: expectedBody,
    });
    expect(state).toBe(serverState);
  });

  it('escapes the session id in the path', async () => {
    await tunePreferenceRadar('a/b c', { locked: false });

    expect(vi.mocked(apiRequest).mock.calls[0][0]).toBe('/memory/radar/a%2Fb%20c/tune');
  });

  it('lets the error notice of a failed change through', async () => {
    vi.mocked(apiRequest).mockRejectedValue(new Error('rejected'));

    await expect(tunePreferenceRadar('chat-1', { recency: 2 })).rejects.toThrow('rejected');
    expect(vi.mocked(apiRequest).mock.calls[0][1]).not.toHaveProperty('silent');
  });
});
