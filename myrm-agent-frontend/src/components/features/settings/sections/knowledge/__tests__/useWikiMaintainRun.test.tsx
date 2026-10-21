/** @vitest-environment jsdom */
import { act, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { WikiMaintainResponse, WikiMaintainStatus } from '@/services/wikiService';

const startMock = vi.fn();
const statusMock = vi.fn();
const cancelMock = vi.fn();

vi.mock('@/services/wikiService', () => ({
  startWikiMaintain: (...args: unknown[]) => startMock(...args),
  getWikiMaintainStatus: (...args: unknown[]) => statusMock(...args),
  cancelWikiMaintain: (...args: unknown[]) => cancelMock(...args),
}));

vi.mock('@/lib/api', () => ({
  ApiError: class ApiError extends Error {
    constructor(
      message: string,
      public code: number = 50001,
    ) {
      super(message);
    }
  },
}));

import { ApiError } from '@/lib/api';
import {
  MAINTAIN_FIRST_POLL_DELAY_MS,
  MAINTAIN_POLL_INTERVAL_MS,
  MAINTAIN_POLL_MAX_CONSECUTIVE_ERRORS,
  useWikiMaintainRun,
} from '../useWikiMaintainRun';

const RESULT: WikiMaintainResponse = {
  issues_found: 1,
  issues_fixed: 0,
  connections_discovered: 3,
  duration_ms: 1000,
  open_actions_count: 0,
  raw_security_removed: 0,
  raw_security_removed_paths: [],
  issues: [],
  ai_unavailable: false,
};

function status(overrides: Partial<WikiMaintainStatus> = {}): WikiMaintainStatus {
  return {
    state: 'idle',
    mode: null,
    phase: null,
    done: 0,
    total: 0,
    cancel_requested: false,
    result: null,
    error_code: null,
    ...overrides,
  };
}

const running = (overrides: Partial<WikiMaintainStatus> = {}) =>
  status({ state: 'running', mode: 'full', ...overrides });

async function tick(times = 1) {
  for (let index = 0; index < times; index += 1) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(MAINTAIN_POLL_INTERVAL_MS);
    });
  }
}

describe('useWikiMaintainRun', () => {
  const onFinished = vi.fn();

  beforeEach(() => {
    vi.useFakeTimers();
    startMock.mockReset();
    statusMock.mockReset();
    cancelMock.mockReset();
    onFinished.mockReset();
    statusMock.mockResolvedValue(status());
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  function mount(agentScopeId: string | null = null) {
    return renderHook(
      (props: { agentScopeId: string | null; onFinished: typeof onFinished }) => useWikiMaintainRun(props),
      {
        initialProps: { agentScopeId, onFinished },
      },
    );
  }

  it('follows a started run through its progress to the result, which is reported exactly once', async () => {
    startMock.mockResolvedValue(running());
    statusMock
      .mockResolvedValueOnce(status()) // resume check on mount
      .mockResolvedValueOnce(running({ phase: 'link_discovery', done: 7, total: 20 }))
      .mockResolvedValueOnce(status({ state: 'succeeded', mode: 'full', result: RESULT }));
    const { result } = mount('agent-1');
    await act(async () => {});

    await act(async () => {
      await result.current.start('full');
    });
    expect(startMock).toHaveBeenCalledWith('full', 'agent-1');
    expect(result.current.isRunning).toBe(true);
    expect(result.current.progress).toBeNull();

    await tick();
    expect(result.current.isRunning).toBe(true);
    expect(result.current.progress).toEqual({ phase: 'link_discovery', done: 7, total: 20 });
    expect(onFinished).not.toHaveBeenCalled();

    await tick();
    expect(result.current.isRunning).toBe(false);
    expect(result.current.progress).toBeNull();
    expect(onFinished).toHaveBeenCalledTimes(1);
    expect(onFinished).toHaveBeenCalledWith({ kind: 'success', mode: 'full', result: RESULT });

    await tick(3);
    expect(statusMock).toHaveBeenCalledTimes(3);
    expect(onFinished).toHaveBeenCalledTimes(1);
  });

  it('looks early at a run that has just started, then settles into the slow pace', async () => {
    startMock.mockResolvedValue(running());
    statusMock.mockResolvedValueOnce(status()).mockResolvedValue(running());
    const { result } = mount();
    await act(async () => {});
    await act(async () => {
      await result.current.start('structural');
    });
    expect(statusMock).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(MAINTAIN_FIRST_POLL_DELAY_MS);
    });
    expect(statusMock).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(MAINTAIN_FIRST_POLL_DELAY_MS);
    });
    expect(statusMock).toHaveBeenCalledTimes(2);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(MAINTAIN_POLL_INTERVAL_MS - MAINTAIN_FIRST_POLL_DELAY_MS);
    });
    expect(statusMock).toHaveBeenCalledTimes(3);
  });

  it('is busy from the click, before the server has answered', async () => {
    let accept: (value: WikiMaintainStatus) => void = () => undefined;
    startMock.mockReturnValue(new Promise<WikiMaintainStatus>((resolve) => (accept = resolve)));
    const { result } = mount();
    await act(async () => {});

    act(() => {
      void result.current.start('structural');
    });
    expect(result.current.isRunning).toBe(true);

    await act(async () => {
      accept(status({ state: 'succeeded', mode: 'structural', result: RESULT }));
    });
    expect(onFinished).toHaveBeenCalledWith({ kind: 'success', mode: 'structural', result: RESULT });
    expect(result.current.isRunning).toBe(false);
  });

  it('reports a compile that blocks the start as compile_busy and any other start error as failed', async () => {
    const { result } = mount();
    await act(async () => {});

    startMock.mockRejectedValueOnce(new ApiError('conflict', 409));
    await act(async () => {
      await result.current.start('full');
    });
    startMock.mockRejectedValueOnce(new ApiError('boom', 500));
    await act(async () => {
      await result.current.start('full');
    });

    expect(onFinished).toHaveBeenNthCalledWith(1, { kind: 'failure', reason: 'compile_busy' });
    expect(onFinished).toHaveBeenNthCalledWith(2, { kind: 'failure', reason: 'failed' });
    expect(result.current.isRunning).toBe(false);
  });

  it.each([
    ['compile_in_progress', 'compile_busy'],
    ['maintain_failed', 'failed'],
    ['maintain_timeout', 'failed'],
  ] as const)('maps the server error code %s to %s', async (errorCode, reason) => {
    startMock.mockResolvedValue(running());
    statusMock
      .mockResolvedValueOnce(status())
      .mockResolvedValueOnce(status({ state: 'failed', mode: 'full', error_code: errorCode }));
    const { result } = mount();
    await act(async () => {});

    await act(async () => {
      await result.current.start('full');
    });
    await tick();

    expect(onFinished).toHaveBeenCalledWith({ kind: 'failure', reason });
    expect(result.current.isRunning).toBe(false);
  });

  it('treats a vanished run (server restarted) as failed', async () => {
    startMock.mockResolvedValue(running());
    statusMock.mockResolvedValueOnce(status()).mockResolvedValueOnce(status());
    const { result } = mount();
    await act(async () => {});

    await act(async () => {
      await result.current.start('full');
    });
    await tick();

    expect(onFinished).toHaveBeenCalledWith({ kind: 'failure', reason: 'failed' });
  });

  it('rides out a few failed polls, then gives up and reports failure', async () => {
    startMock.mockResolvedValue(running());
    statusMock.mockResolvedValueOnce(status());
    const { result } = mount();
    await act(async () => {});
    await act(async () => {
      await result.current.start('full');
    });

    statusMock.mockRejectedValue(new Error('network down'));
    await tick(MAINTAIN_POLL_MAX_CONSECUTIVE_ERRORS - 1);
    expect(onFinished).not.toHaveBeenCalled();
    expect(result.current.isRunning).toBe(true);

    statusMock.mockResolvedValueOnce(running({ phase: 'drift_review', done: 1, total: 5 }));
    await tick();
    expect(result.current.progress).toEqual({ phase: 'drift_review', done: 1, total: 5 });

    statusMock.mockRejectedValue(new Error('network down'));
    await tick(MAINTAIN_POLL_MAX_CONSECUTIVE_ERRORS);
    expect(onFinished).toHaveBeenCalledTimes(1);
    expect(onFinished).toHaveBeenCalledWith({ kind: 'failure', reason: 'failed' });
    expect(result.current.isRunning).toBe(false);
  });

  it('picks a run in flight back up on mount and reports its result', async () => {
    statusMock
      .mockResolvedValueOnce(running({ phase: 'link_discovery', done: 3, total: 20 }))
      .mockResolvedValueOnce(status({ state: 'succeeded', mode: 'full', result: RESULT }));

    const { result } = mount('agent-1');
    await act(async () => {});

    expect(statusMock).toHaveBeenCalledWith('agent-1');
    expect(result.current.isRunning).toBe(true);
    expect(result.current.progress).toEqual({ phase: 'link_discovery', done: 3, total: 20 });

    await tick();
    expect(onFinished).toHaveBeenCalledWith({ kind: 'success', mode: 'full', result: RESULT });
    expect(result.current.isRunning).toBe(false);
  });

  it('stays quiet about a run that finished before the page was opened', async () => {
    statusMock.mockResolvedValue(status({ state: 'succeeded', mode: 'full', result: RESULT }));

    const { result } = mount();
    await act(async () => {});
    await tick(2);

    expect(result.current.isRunning).toBe(false);
    expect(onFinished).not.toHaveBeenCalled();
    expect(statusMock).toHaveBeenCalledTimes(1);
  });

  it('stops polling and reports nothing once unmounted', async () => {
    statusMock.mockResolvedValue(running());
    const { unmount } = mount();
    await act(async () => {});
    await tick();
    const callsBefore = statusMock.mock.calls.length;

    unmount();
    await tick(3);

    expect(statusMock).toHaveBeenCalledTimes(callsBefore);
    expect(onFinished).not.toHaveBeenCalled();
  });

  it('starts no polling when it is unmounted while the start request is in flight', async () => {
    let accept: (value: WikiMaintainStatus) => void = () => undefined;
    startMock.mockReturnValue(new Promise<WikiMaintainStatus>((resolve) => (accept = resolve)));
    const { result, unmount } = mount();
    await act(async () => {});
    act(() => {
      void result.current.start('full');
    });
    const callsBefore = statusMock.mock.calls.length;

    unmount();
    await act(async () => {
      accept(running());
    });
    await tick(3);

    expect(statusMock).toHaveBeenCalledTimes(callsBefore);
    expect(onFinished).not.toHaveBeenCalled();
  });

  it('follows the agent scope: a run of the previous scope neither shows nor reports', async () => {
    statusMock.mockImplementation((scope: string | null) =>
      Promise.resolve(scope === 'agent-1' ? running() : status()),
    );
    const { result, rerender } = mount('agent-1');
    await act(async () => {});
    expect(result.current.isRunning).toBe(true);

    rerender({ agentScopeId: 'agent-2', onFinished });
    await act(async () => {});
    await tick(2);

    expect(statusMock).toHaveBeenCalledWith('agent-2');
    expect(result.current.isRunning).toBe(false);
    expect(onFinished).not.toHaveBeenCalled();
  });

  it('reports to the latest callback without restarting the polling when the callback identity changes', async () => {
    statusMock
      .mockResolvedValueOnce(running())
      .mockResolvedValueOnce(running())
      .mockResolvedValueOnce(status({ state: 'succeeded', mode: 'full', result: RESULT }));
    const { rerender } = mount();
    await act(async () => {});
    const latest = vi.fn();

    rerender({ agentScopeId: null, onFinished: latest });
    await act(async () => {});
    expect(statusMock).toHaveBeenCalledTimes(1);
    await tick(2);

    expect(statusMock).toHaveBeenCalledTimes(3);
    expect(latest).toHaveBeenCalledTimes(1);
    expect(onFinished).not.toHaveBeenCalled();
  });

  describe('cancelling', () => {
    async function startFullRun() {
      startMock.mockResolvedValue(running());
      statusMock.mockResolvedValueOnce(status());
      const hook = mount();
      await act(async () => {});
      await act(async () => {
        await hook.result.current.start('full');
      });
      return hook;
    }

    it('shows the run as stopping at once, then reports what it wrote as cancelled', async () => {
      const { result } = await startFullRun();
      expect(result.current.canCancel).toBe(true);
      expect(result.current.isCancelling).toBe(false);
      cancelMock.mockResolvedValue(running({ cancel_requested: true }));

      await act(async () => {
        await result.current.cancel();
      });

      expect(cancelMock).toHaveBeenCalledWith(null);
      expect(result.current.isRunning).toBe(true);
      expect(result.current.canCancel).toBe(false);
      expect(result.current.isCancelling).toBe(true);
      expect(onFinished).not.toHaveBeenCalled();

      statusMock.mockResolvedValueOnce(status({ state: 'cancelled', mode: 'full', result: RESULT }));
      await tick();

      expect(onFinished).toHaveBeenCalledTimes(1);
      expect(onFinished).toHaveBeenCalledWith({ kind: 'cancelled', mode: 'full', result: RESULT });
      expect(result.current.isRunning).toBe(false);
      expect(result.current.isCancelling).toBe(false);
    });

    it('offers no cancel for a structural run, which ends within moments', async () => {
      startMock.mockResolvedValue(running({ mode: 'structural' }));
      statusMock.mockResolvedValueOnce(status());
      const { result } = mount();
      await act(async () => {});

      await act(async () => {
        await result.current.start('structural');
      });

      expect(result.current.isRunning).toBe(true);
      expect(result.current.canCancel).toBe(false);
    });

    it('keeps following the run and stays cancellable when the cancel request fails', async () => {
      const { result } = await startFullRun();
      cancelMock.mockRejectedValue(new Error('network down'));

      await act(async () => {
        await expect(result.current.cancel()).rejects.toThrow('network down');
      });

      expect(result.current.isRunning).toBe(true);
      expect(result.current.canCancel).toBe(true);
      expect(result.current.isCancelling).toBe(false);
      expect(onFinished).not.toHaveBeenCalled();
    });

    it('does not bring back a run that ended while the cancel request was still on its way', async () => {
      const { result } = await startFullRun();
      let answer: (value: WikiMaintainStatus) => void = () => undefined;
      cancelMock.mockReturnValue(new Promise<WikiMaintainStatus>((resolve) => (answer = resolve)));
      let pending: Promise<void> = Promise.resolve();
      act(() => {
        pending = result.current.cancel();
      });

      statusMock.mockResolvedValueOnce(status({ state: 'succeeded', mode: 'full', result: RESULT }));
      await tick();
      expect(result.current.isRunning).toBe(false);

      await act(async () => {
        answer(running({ cancel_requested: true }));
        await pending;
      });

      expect(result.current.isRunning).toBe(false);
      expect(result.current.isCancelling).toBe(false);
      expect(onFinished).toHaveBeenCalledTimes(1);
    });

    it('shows a run that was cancelled before the page reloaded as stopping', async () => {
      statusMock
        .mockResolvedValueOnce(running({ cancel_requested: true }))
        .mockResolvedValue(running({ cancel_requested: true }));

      const { result } = mount();
      await act(async () => {});

      expect(result.current.isRunning).toBe(true);
      expect(result.current.isCancelling).toBe(true);
      expect(result.current.canCancel).toBe(false);
    });

    it('reports a cancelled run that wrote nothing like any other cancelled run', async () => {
      const { result } = await startFullRun();
      statusMock.mockResolvedValueOnce(
        status({ state: 'cancelled', mode: 'full', result: { ...RESULT, connections_discovered: 0 } }),
      );

      await tick();

      expect(onFinished).toHaveBeenCalledWith({
        kind: 'cancelled',
        mode: 'full',
        result: { ...RESULT, connections_discovered: 0 },
      });
      expect(result.current.isRunning).toBe(false);
    });
  });
});
