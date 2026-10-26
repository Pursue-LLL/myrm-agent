import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const fetchWithTimeout = vi.fn();
const fetchOnPageExit = vi.fn();

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: (...args: unknown[]) => fetchWithTimeout(...args),
  fetchOnPageExit: (...args: unknown[]) => fetchOnPageExit(...args),
}));

import useUserControlStore from '../useUserControlStore';

const TAKEOVER = '/webui/vnc/takeover';
const RESUME = '/webui/vnc/resume';
const BEAT_MS = 30_000;

function ok(body: unknown = {}) {
  return { ok: true, status: 200, json: async () => body };
}

function calls(): string[] {
  return fetchWithTimeout.mock.calls.map(
    ([url, init]) => `${(init as RequestInit | undefined)?.method ?? 'GET'} ${url}`,
  );
}

describe('useUserControlStore', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    fetchWithTimeout.mockReset();
    fetchOnPageExit.mockReset();
    fetchWithTimeout.mockResolvedValue(ok({ state: 'user_takeover', learned: false }));
  });

  afterEach(async () => {
    fetchWithTimeout.mockResolvedValue(ok());
    await useUserControlStore.getState().release();
    vi.useRealTimers();
  });

  it('holds control once the server grants it', async () => {
    const granted = await useUserControlStore.getState().acquire('captcha');

    expect(granted).toBe(true);
    expect(useUserControlStore.getState().held).toBe(true);
    expect(fetchWithTimeout).toHaveBeenCalledWith(
      TAKEOVER,
      expect.objectContaining({ method: 'POST', body: JSON.stringify({ reason: 'captcha' }) }),
    );
  });

  it.each([
    ['refuses', () => fetchWithTimeout.mockResolvedValue({ ok: false, status: 501 })],
    ['cannot be reached', () => fetchWithTimeout.mockRejectedValue(new Error('network'))],
  ])('does not claim control when the server %s', async (_label, arrange) => {
    arrange();

    const granted = await useUserControlStore.getState().acquire('captcha');

    expect(granted).toBe(false);
    expect(useUserControlStore.getState().held).toBe(false);
  });

  it('renews the lease on every beat while held', async () => {
    await useUserControlStore.getState().acquire();
    fetchWithTimeout.mockClear();

    await vi.advanceTimersByTimeAsync(BEAT_MS);
    expect(calls()).toEqual([`GET ${TAKEOVER}`, `POST ${TAKEOVER}`]);

    await vi.advanceTimersByTimeAsync(BEAT_MS);
    expect(calls()).toHaveLength(4);
    expect(useUserControlStore.getState().held).toBe(true);
  });

  it('stops claiming control when the server says the agent has it back', async () => {
    await useUserControlStore.getState().acquire();
    fetchWithTimeout.mockClear();
    fetchWithTimeout.mockResolvedValue(ok({ state: 'agent_active' }));

    await vi.advanceTimersByTimeAsync(BEAT_MS);

    expect(useUserControlStore.getState().held).toBe(false);
    expect(calls()).toEqual([`GET ${TAKEOVER}`]);

    fetchWithTimeout.mockClear();
    await vi.advanceTimersByTimeAsync(BEAT_MS * 3);
    expect(fetchWithTimeout).not.toHaveBeenCalled();
  });

  it('keeps holding through a failed beat and retries on the next one', async () => {
    await useUserControlStore.getState().acquire();
    fetchWithTimeout.mockClear();
    fetchWithTimeout.mockRejectedValueOnce(new Error('network'));

    await vi.advanceTimersByTimeAsync(BEAT_MS);
    expect(useUserControlStore.getState().held).toBe(true);

    await vi.advanceTimersByTimeAsync(BEAT_MS);
    expect(calls().filter((call) => call === `POST ${TAKEOVER}`)).toHaveLength(1);
  });

  it('hands back, stops renewing and reports what the agent learned', async () => {
    await useUserControlStore.getState().acquire();
    fetchWithTimeout.mockClear();
    fetchWithTimeout.mockResolvedValue(ok({ state: 'agent_active', learned: true }));

    const result = await useUserControlStore.getState().release();

    expect(result).toEqual({ state: 'agent_active', learned: true });
    expect(useUserControlStore.getState().held).toBe(false);
    expect(fetchWithTimeout).toHaveBeenCalledWith(RESUME, { method: 'POST' });

    fetchWithTimeout.mockClear();
    await vi.advanceTimersByTimeAsync(BEAT_MS * 3);
    expect(fetchWithTimeout).not.toHaveBeenCalled();
  });

  it('keeps holding and keeps renewing when the hand back fails, so the person can retry', async () => {
    await useUserControlStore.getState().acquire();
    fetchWithTimeout.mockResolvedValue({ ok: false, status: 503 });

    await expect(useUserControlStore.getState().release()).rejects.toThrow('503');

    expect(useUserControlStore.getState().held).toBe(true);
    fetchWithTimeout.mockClear();
    fetchWithTimeout.mockResolvedValue(ok({ state: 'user_takeover' }));
    await vi.advanceTimersByTimeAsync(BEAT_MS);
    expect(calls()).toEqual([`GET ${TAKEOVER}`, `POST ${TAKEOVER}`]);
  });

  it('never lets a renewal land after the hand back', async () => {
    await useUserControlStore.getState().acquire();
    fetchWithTimeout.mockClear();

    let answerState: (value: unknown) => void = () => undefined;
    fetchWithTimeout.mockImplementation((url: string, init?: RequestInit) => {
      if (url === TAKEOVER && !init?.method) {
        return new Promise((resolve) => {
          answerState = resolve;
        });
      }
      return Promise.resolve(ok({ state: 'user_takeover', learned: false }));
    });

    await vi.advanceTimersByTimeAsync(BEAT_MS);
    const handingBack = useUserControlStore.getState().release();
    answerState(ok({ state: 'user_takeover' }));
    await handingBack;

    expect(calls()).toEqual([`GET ${TAKEOVER}`, `POST ${TAKEOVER}`, `POST ${RESUME}`]);
  });

  it('hands control back at once when the page goes away', async () => {
    await useUserControlStore.getState().acquire();
    fetchWithTimeout.mockClear();

    window.dispatchEvent(new Event('pagehide'));

    expect(fetchOnPageExit).toHaveBeenCalledWith(RESUME, { method: 'POST' });
    expect(fetchWithTimeout).not.toHaveBeenCalled();
  });

  it('has nothing to hand back on pagehide when the person never held control', () => {
    window.dispatchEvent(new Event('pagehide'));

    expect(fetchOnPageExit).not.toHaveBeenCalled();
    expect(fetchWithTimeout).not.toHaveBeenCalled();
  });
});
