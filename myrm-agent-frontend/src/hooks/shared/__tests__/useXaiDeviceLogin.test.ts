import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { XaiOAuthPollResponse, XaiOAuthStartResponse } from '@/services/xai-oauth';

const { mockStart, mockPoll, mockConnect } = vi.hoisted(() => ({
  mockStart: vi.fn(),
  mockPoll: vi.fn(),
  mockConnect: vi.fn(),
}));

vi.mock('@/services/xai-oauth', () => ({ startXaiOAuth: mockStart, pollXaiOAuth: mockPoll }));
vi.mock('@/store/config/providerSubscription', () => ({ connectProviderSubscription: mockConnect }));

import { useXaiDeviceLogin } from '../useXaiDeviceLogin';

const STARTED: XaiOAuthStartResponse = {
  user_code: 'ABCD-1234',
  verification_uri: 'https://x.ai/device',
  verification_uri_complete: 'https://x.ai/device?code=ABCD-1234',
  expires_in: 600,
  interval: 5,
};

const pending: XaiOAuthPollResponse = { status: 'pending' };

describe('useXaiDeviceLogin', () => {
  const onConnected = vi.fn();
  const onFailed = vi.fn();

  function setup() {
    return renderHook(() => useXaiDeviceLogin({ onConnected, onFailed }));
  }

  async function startLogin(hook: ReturnType<typeof setup>): Promise<string | null> {
    let url: string | null = null;
    await act(async () => {
      url = await hook.result.current.start();
    });
    return url;
  }

  async function advance(ms: number) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  }

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();
    mockStart.mockResolvedValue(STARTED);
    mockPoll.mockResolvedValue(pending);
    mockConnect.mockResolvedValue(undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe('starting', () => {
    it('exposes the code and the pre-filled verification page, and returns that page to the caller', async () => {
      const hook = setup();
      expect(hook.result.current).toMatchObject({ phase: 'idle', userCode: null, verificationUrl: null });

      const url = await startLogin(hook);

      expect(url).toBe('https://x.ai/device?code=ABCD-1234');
      expect(hook.result.current).toMatchObject({
        phase: 'waiting',
        userCode: 'ABCD-1234',
        verificationUrl: 'https://x.ai/device?code=ABCD-1234',
      });
    });

    it('falls back to the plain verification page when the server offers no pre-filled one', async () => {
      mockStart.mockResolvedValue({ ...STARTED, verification_uri_complete: '' });
      const hook = setup();

      expect(await startLogin(hook)).toBe('https://x.ai/device');
    });

    it('reports the starting phase while the code is requested', async () => {
      mockStart.mockReturnValue(new Promise(() => {}));
      const hook = setup();

      act(() => {
        void hook.result.current.start();
      });

      expect(hook.result.current.phase).toBe('starting');
    });

    it('ignores a second start while a login is running', async () => {
      const hook = setup();
      await startLogin(hook);

      expect(await startLogin(hook)).toBeNull();
      expect(mockStart).toHaveBeenCalledOnce();
    });

    it('ignores a second start while the first request is still in flight', async () => {
      mockStart.mockReturnValue(new Promise(() => {}));
      const hook = setup();

      await act(async () => {
        void hook.result.current.start();
        expect(await hook.result.current.start()).toBeNull();
      });

      expect(mockStart).toHaveBeenCalledOnce();
    });

    it.each([
      ['the request fails', () => mockStart.mockRejectedValue(new Error('500'))],
      ['the answer has no code', () => mockStart.mockResolvedValue({ ...STARTED, user_code: '' })],
      ['the answer has no verification page', () => mockStart.mockResolvedValue({ ...STARTED, verification_uri: '' })],
    ])('reports startFailed when %s, and allows another attempt', async (_label, arrange) => {
      arrange();
      const hook = setup();

      expect(await startLogin(hook)).toBeNull();

      expect(onFailed).toHaveBeenCalledExactlyOnceWith('startFailed');
      expect(hook.result.current).toMatchObject({ phase: 'idle', userCode: null });
      expect(mockPoll).not.toHaveBeenCalled();

      mockStart.mockResolvedValue(STARTED);
      expect(await startLogin(hook)).toBe('https://x.ai/device?code=ABCD-1234');
    });
  });

  describe('polling schedule', () => {
    it('polls with the code every interval the server asked for', async () => {
      mockStart.mockResolvedValue({ ...STARTED, interval: 7 });
      const hook = setup();
      await startLogin(hook);

      await advance(6999);
      expect(mockPoll).not.toHaveBeenCalled();
      await advance(1);
      expect(mockPoll).toHaveBeenCalledExactlyOnceWith('ABCD-1234');
      await advance(7000);
      expect(mockPoll).toHaveBeenCalledTimes(2);
    });

    it.each([
      ['is missing', 0, 5000],
      ['is below one second', 0.2, 1000],
    ])('applies a sane interval when the server value %s', async (_label, interval, expectedMs) => {
      mockStart.mockResolvedValue({ ...STARTED, interval });
      const hook = setup();
      await startLogin(hook);

      await advance(expectedMs - 1);
      expect(mockPoll).not.toHaveBeenCalled();
      await advance(1);
      expect(mockPoll).toHaveBeenCalledOnce();
    });

    it('slows down by five seconds for good when the server asks to', async () => {
      mockPoll.mockResolvedValueOnce({ status: 'pending', slow_down: true }).mockResolvedValue(pending);
      const hook = setup();
      await startLogin(hook);

      await advance(5000);
      expect(mockPoll).toHaveBeenCalledTimes(1);

      await advance(9999);
      expect(mockPoll).toHaveBeenCalledTimes(1);
      await advance(1);
      expect(mockPoll).toHaveBeenCalledTimes(2);

      // The wider interval stays: a later plain pending answer does not bring the old pace back.
      await advance(9999);
      expect(mockPoll).toHaveBeenCalledTimes(2);
      await advance(1);
      expect(mockPoll).toHaveBeenCalledTimes(3);
    });

    it('keeps polling through failed requests', async () => {
      mockPoll.mockRejectedValueOnce(new Error('network')).mockRejectedValueOnce(new Error('network'));
      const hook = setup();
      await startLogin(hook);

      await advance(15000);

      expect(mockPoll).toHaveBeenCalledTimes(3);
      expect(onFailed).not.toHaveBeenCalled();
      expect(hook.result.current.phase).toBe('waiting');
    });
  });

  describe('outcome', () => {
    it('applies the connected subscription once and reports it, then stops polling', async () => {
      mockPoll.mockResolvedValue({ status: 'success' });
      const hook = setup();
      await startLogin(hook);

      await advance(5000);

      expect(mockConnect).toHaveBeenCalledExactlyOnceWith('xai');
      expect(onConnected).toHaveBeenCalledOnce();
      expect(onFailed).not.toHaveBeenCalled();
      expect(hook.result.current).toMatchObject({ phase: 'idle', userCode: null, verificationUrl: null });

      await advance(30000);
      expect(mockPoll).toHaveBeenCalledOnce();
    });

    it('reports the connection even when applying it to the store fails', async () => {
      mockPoll.mockResolvedValue({ status: 'success' });
      mockConnect.mockRejectedValue(new Error('store write failed'));
      vi.spyOn(console, 'error').mockImplementation(() => {});
      const hook = setup();
      await startLogin(hook);

      await advance(5000);

      expect(onConnected).toHaveBeenCalledOnce();
    });

    it.each(['expired', 'denied'] as const)(
      'reports %s and stops polling without touching the provider',
      async (status) => {
        mockPoll.mockResolvedValue({ status, error: 'raw server text that must not surface' });
        const hook = setup();
        await startLogin(hook);

        await advance(5000);
        await advance(30000);

        expect(onFailed).toHaveBeenCalledExactlyOnceWith(status);
        expect(onConnected).not.toHaveBeenCalled();
        expect(mockConnect).not.toHaveBeenCalled();
        expect(mockPoll).toHaveBeenCalledOnce();
        expect(hook.result.current.phase).toBe('idle');
      },
    );

    it('times out when the code lifetime ends without an answer', async () => {
      mockStart.mockResolvedValue({ ...STARTED, expires_in: 20 });
      const hook = setup();
      await startLogin(hook);

      await advance(15000);
      expect(mockPoll).toHaveBeenCalledTimes(3);
      expect(onFailed).not.toHaveBeenCalled();

      await advance(5000);

      expect(onFailed).toHaveBeenCalledExactlyOnceWith('timeout');
      expect(mockPoll).toHaveBeenCalledTimes(3);
      expect(hook.result.current.phase).toBe('idle');
    });

    it('assumes the usual ten-minute lifetime when the server gives none', async () => {
      mockStart.mockResolvedValue({ ...STARTED, expires_in: 0 });
      const hook = setup();
      await startLogin(hook);

      await advance(599_000);
      expect(onFailed).not.toHaveBeenCalled();
      await advance(6000);

      expect(onFailed).toHaveBeenCalledExactlyOnceWith('timeout');
    });
  });

  describe('abandoning a login', () => {
    it('stops polling and reports nothing after cancel', async () => {
      const hook = setup();
      await startLogin(hook);

      act(() => hook.result.current.cancel());
      await advance(60000);

      expect(mockPoll).not.toHaveBeenCalled();
      expect(onFailed).not.toHaveBeenCalled();
      expect(hook.result.current).toMatchObject({ phase: 'idle', userCode: null, verificationUrl: null });
    });

    it('allows a fresh login after cancel', async () => {
      const hook = setup();
      await startLogin(hook);
      act(() => hook.result.current.cancel());

      expect(await startLogin(hook)).toBe('https://x.ai/device?code=ABCD-1234');
      expect(mockStart).toHaveBeenCalledTimes(2);
    });

    it('stops polling and reports nothing after unmount', async () => {
      const hook = setup();
      await startLogin(hook);

      hook.unmount();
      await advance(60000);

      expect(mockPoll).not.toHaveBeenCalled();
      expect(onFailed).not.toHaveBeenCalled();
      expect(onConnected).not.toHaveBeenCalled();
    });

    it('ignores a code that arrives after cancel', async () => {
      let resolveStart!: (value: XaiOAuthStartResponse) => void;
      mockStart.mockReturnValue(new Promise<XaiOAuthStartResponse>((resolve) => (resolveStart = resolve)));
      const hook = setup();
      let started: Promise<string | null> = Promise.resolve(null);
      act(() => {
        started = hook.result.current.start();
      });

      act(() => hook.result.current.cancel());
      await act(async () => {
        resolveStart(STARTED);
        expect(await started).toBeNull();
      });
      await advance(60000);

      expect(hook.result.current).toMatchObject({ phase: 'idle', userCode: null });
      expect(mockPoll).not.toHaveBeenCalled();
    });

    it('ignores an approval that is answered after cancel', async () => {
      let resolvePoll!: (value: XaiOAuthPollResponse) => void;
      mockPoll.mockReturnValueOnce(new Promise<XaiOAuthPollResponse>((resolve) => (resolvePoll = resolve)));
      const hook = setup();
      await startLogin(hook);
      await advance(5000);
      expect(mockPoll).toHaveBeenCalledOnce();

      act(() => hook.result.current.cancel());
      await act(async () => resolvePoll({ status: 'success' }));

      expect(mockConnect).not.toHaveBeenCalled();
      expect(onConnected).not.toHaveBeenCalled();
    });
  });

  it('reports to the callbacks of the latest render', async () => {
    mockPoll.mockResolvedValue({ status: 'success' });
    const later = vi.fn();
    const hook = renderHook(
      (props: { onConnected: () => void }) => useXaiDeviceLogin({ onConnected: props.onConnected, onFailed }),
      { initialProps: { onConnected } },
    );
    await act(async () => {
      await hook.result.current.start();
    });

    hook.rerender({ onConnected: later });
    await advance(5000);

    expect(later).toHaveBeenCalledOnce();
    expect(onConnected).not.toHaveBeenCalled();
  });
});
