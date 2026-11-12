/**
 * The read loop's own guards: the liveness budget that hands a silent connection to the recovery, a silent
 * first frame, malformed frames and an exhausted recovery deadline.
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import {
  armStreamHandlers,
  createActions,
  createBaseState,
  createPushedResponse,
  createSseResponse,
  eventually,
  HEARTBEAT_FRAME,
  installStreamConsumerLifecycle,
  mockHandleMessageStream,
  mockParseSseEnvelope,
  mockRecoverPendingApprovals,
  observe,
} from './streamConsumerTestKit';
import { consumeStream, STREAM_LIVENESS_BUDGET_MS } from '../consumeStream';
import { StreamInterruptedError } from '../streamErrors';

installStreamConsumerLifecycle();

describe('the liveness budget of a read', () => {
  // The server's stream buffer sends its heartbeat after this much idle time (`HEARTBEAT_INTERVAL_SEC`).
  const SERVER_HEARTBEAT_INTERVAL_MS = 15_000;

  /** Swaps the native timeout signal every read waits under for one the test expires by hand. */
  function takeOverReadBudgets(): { durations: number[]; expire: (read: number) => void } {
    const durations: number[] = [];
    const controllers: AbortController[] = [];
    vi.spyOn(AbortSignal, 'timeout').mockImplementation((milliseconds: number) => {
      durations.push(milliseconds);
      const controller = new AbortController();
      controllers.push(controller);
      return controller.signal;
    });
    return { durations, expire: (read) => controllers[read].abort() };
  }

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('is three of the intervals in which the server sends its heartbeat', () => {
    expect(STREAM_LIVENESS_BUDGET_MS).toBe(3 * SERVER_HEARTBEAT_INTERVAL_MS);
  });

  it('hands a connection that delivers nothing within it to the recovery as an interrupted stream', async () => {
    const budgets = takeOverReadBudgets();
    const state = createBaseState();
    const actions = createActions(state);
    const stream = createPushedResponse();
    armStreamHandlers();

    const run = observe(consumeStream(stream.response, 'hello', state, actions, new AbortController(), false, ''));
    // The first read returned the event; the second one waits, under the same budget.
    await eventually(() => expect(budgets.durations).toHaveLength(2));
    expect(budgets.durations).toEqual([STREAM_LIVENESS_BUDGET_MS, STREAM_LIVENESS_BUDGET_MS]);

    budgets.expire(1);
    await eventually(() => expect(run.isSettled()).toBe(true));

    expect(run.error()).toBeInstanceOf(StreamInterruptedError);
    // The turn belongs to the recovery from here on: nothing marks the page idle before it has attached.
    expect(actions.setLoading).not.toHaveBeenCalled();
    expect(mockRecoverPendingApprovals).toHaveBeenCalledTimes(1);
  });

  it('starts over with every chunk, a heartbeat included, and ignores the budget of a read that has returned', async () => {
    const budgets = takeOverReadBudgets();
    const state = createBaseState();
    const stream = createPushedResponse();
    armStreamHandlers();

    const run = observe(
      consumeStream(stream.response, 'hello', state, createActions(state), new AbortController(), false, ''),
    );
    await eventually(() => expect(budgets.durations).toHaveLength(2));

    stream.push(HEARTBEAT_FRAME);
    // The heartbeat answered the second read; the third one waits under a fresh budget.
    await eventually(() => expect(budgets.durations).toHaveLength(3));

    budgets.expire(1);
    await new Promise<void>((resolve) => setTimeout(resolve, 20));
    expect(run.isSettled()).toBe(false);

    budgets.expire(2);
    await eventually(() => expect(run.isSettled()).toBe(true));
    expect(run.error()).toBeInstanceOf(StreamInterruptedError);
    expect(mockHandleMessageStream).toHaveBeenCalledTimes(1);
  });
});

describe('consumeStream stall / malformed-frame resilience', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('turns a silent first frame into StreamInterruptedError instead of hanging forever', async () => {
    const originalTimeout = AbortSignal.timeout.bind(AbortSignal);
    const spy = vi
      .spyOn(AbortSignal, 'timeout')
      .mockImplementation((() => originalTimeout(1)) as unknown as typeof AbortSignal.timeout);
    try {
      const state = createBaseState();
      const actions = createActions(state);
      const silent = new Response(
        new ReadableStream<Uint8Array>({
          start() {
            /* never enqueues and never closes: the reader stays pending until cancelled */
          },
        }),
      );

      await expect(
        consumeStream(silent, 'hello', state, actions, new AbortController(), false, ''),
      ).rejects.toBeInstanceOf(StreamInterruptedError);
    } finally {
      spy.mockRestore();
    }
  });

  it('skips a malformed SSE payload without invoking the reducer', async () => {
    mockHandleMessageStream.mockClear();
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    mockParseSseEnvelope.mockReturnValue(null);
    const state = createBaseState();
    const actions = createActions(state);

    await consumeStream(
      createSseResponse('data: {not-json}\n\n'),
      'hello',
      state,
      actions,
      new AbortController(),
      false,
      '',
    );

    expect(mockHandleMessageStream).not.toHaveBeenCalled();
    expect(warn).toHaveBeenCalled();
  });

  it('stops when the recovery deadline has already passed', async () => {
    const state = createBaseState();
    const actions = createActions(state);

    const result = await consumeStream(
      createSseResponse('data: {"type":"heartbeat"}\n\n'),
      'hello',
      state,
      actions,
      new AbortController(),
      false,
      '',
      { maxWaitMs: 0 },
    );

    expect(result.stoppedEarly).toBe(true);
  });
});
