/**
 * A goal control says what became of it in one of four ways, the same for the card, the panel and `/goal`.
 *
 * Real scenario: the user pauses a goal and presses resume a moment later. The goal's last step is still winding down,
 * so the server refuses (409) and the goal stays paused; that is "try again in a moment", not "resume failed".
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { fetchMock, riskHeld } = vi.hoisted(() => ({ fetchMock: vi.fn(), riskHeld: vi.fn() }));
vi.mock('@/lib/api', () => ({ fetchWithTimeout: fetchMock }));
vi.mock('@/services/riskHeldToast', () => ({ riskHeldErrorFromResponse: riskHeld }));

import { postGoalAction } from '../goalActionClient';

const answers = (status: number) => fetchMock.mockResolvedValue(new Response('{}', { status }));

describe('postGoalAction', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    riskHeld.mockResolvedValue(null);
    vi.spyOn(console, 'error').mockImplementation(() => undefined);
  });

  it('posts the action to the chat of the goal, with a trimmed note only when there is one', async () => {
    answers(200);

    await postGoalAction('chat-1', 'pause', '  waiting for design  ');
    await postGoalAction('chat-1', 'cancel', '   ');

    expect(fetchMock.mock.calls.map(([url, init]) => [url, JSON.parse(String((init as RequestInit).body))])).toEqual([
      ['/goals/chat-1/status', { action: 'pause', note: 'waiting for design' }],
      ['/goals/chat-1/status', { action: 'cancel' }],
    ]);
  });

  it('is done once the server took the action', async () => {
    answers(200);

    expect(await postGoalAction('chat-1', 'resume')).toBe('done');
  });

  it.each(['resume', 'unwait'] as const)(
    'is busy when the server refuses a %s while the last step finishes',
    async (action) => {
      answers(409);

      expect(await postGoalAction('chat-1', action)).toBe('busy');
    },
  );

  it.each(['pause', 'cancel', 'approve', 'reject'] as const)(
    'is a plain failure when %s is refused with a conflict',
    async (action) => {
      answers(409);

      expect(await postGoalAction('chat-1', action)).toBe('failed');
    },
  );

  it.each([404, 500])('fails on HTTP %i', async (status) => {
    answers(status);

    expect(await postGoalAction('chat-1', 'resume')).toBe('failed');
  });

  it('is held, once explained, when a risk rule holds the note', async () => {
    answers(400);
    riskHeld.mockResolvedValue(new Error('held'));

    expect(await postGoalAction('chat-1', 'reject', 'key sk-AAAAAABBBBBBCCCCCCDDDD-0')).toBe('held');
    expect(riskHeld).toHaveBeenCalledTimes(1);
  });

  it('fails instead of throwing when the network is down', async () => {
    fetchMock.mockRejectedValue(new Error('offline'));

    expect(await postGoalAction('chat-1', 'pause')).toBe('failed');
  });
});
