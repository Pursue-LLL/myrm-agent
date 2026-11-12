/**
 * What the stream consumer does once the user stops the turn: pending reads, retry waits and re-attaches
 * end at once and report the stop itself.
 */
import { describe, expect, it, vi } from 'vitest';
import {
  armStreamHandlers,
  createAbortFailingResponse,
  createActions,
  createBaseState,
  createInterruptedResponse,
  createSilentResponse,
  createSseResponse,
  eventually,
  installStreamConsumerLifecycle,
  mockAttachToChat,
  mockCreateMessageRequest,
  mockHandleMessageStream,
  observe,
  STOP_TEST_EVENT,
} from './streamConsumerTestKit';
import { consumeStream } from '../consumeStream';
import { executeStreamWithRetry } from '../streamConsumer';

installStreamConsumerLifecycle();

describe('when the user stops the turn', () => {
  it('never starts reading for a turn that was already stopped, and raises a genuine AbortError', async () => {
    const state = createBaseState();
    const abortController = new AbortController();
    abortController.abort();
    armStreamHandlers();
    // A stream without data would keep a started read waiting for good: no abort event fires for a signal that is
    // already aborted.
    const response = new Response(new ReadableStream<Uint8Array>({ start: () => undefined }), {
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
    });

    const run = observe(consumeStream(response, 'hello', state, createActions(state), abortController, false, ''));
    await eventually(() => expect(run.isSettled()).toBe(true));

    expect(run.error()).toMatchObject({ name: 'AbortError' });
    expect(mockHandleMessageStream).not.toHaveBeenCalled();
  });

  it('ends a pending read at once and leaves no watchdog heal behind', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const onCancel = vi.fn();
    const state = createBaseState();
    const actions = createActions(state);
    const abortController = new AbortController();
    armStreamHandlers();

    const run = observe(
      consumeStream(createSilentResponse(onCancel), 'hello', state, actions, abortController, false, ''),
    );
    // The first event is consumed; the consumer then waits for the next chunk.
    await eventually(() => expect(mockHandleMessageStream).toHaveBeenCalledTimes(1));

    abortController.abort();
    // Far below the liveness budget: only the stop itself can end the consumer this early.
    await vi.advanceTimersByTimeAsync(100);

    expect(run.isSettled()).toBe(true);
    expect(run.error()).toMatchObject({ name: 'AbortError' });
    expect(onCancel).toHaveBeenCalledTimes(1);
    // The cancelled reader ends the read as an end of stream; that must not heal the turn the user stopped.
    expect(actions.setLoading).not.toHaveBeenCalled();
    expect(actions._processSuggestions).not.toHaveBeenCalled();
  });

  it('reports a read that failed because of the stop as the stop itself, not as an interrupted stream', async () => {
    const state = createBaseState();
    const abortController = new AbortController();
    armStreamHandlers();

    const run = observe(
      consumeStream(
        createAbortFailingResponse(abortController.signal),
        'hello',
        state,
        createActions(state),
        abortController,
        false,
        '',
      ),
    );
    await eventually(() => expect(mockHandleMessageStream).toHaveBeenCalledTimes(1));

    abortController.abort();
    await eventually(() => expect(run.isSettled()).toBe(true));

    expect(run.error()).toMatchObject({ name: 'AbortError' });
  });

  it('detaches its abort listener once the stream has been consumed', async () => {
    const state = createBaseState();
    const abortController = new AbortController();
    const detach = vi.spyOn(abortController.signal, 'removeEventListener');
    armStreamHandlers();
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);

    try {
      await consumeStream(
        createSseResponse(STOP_TEST_EVENT),
        'hello',
        state,
        createActions(state),
        abortController,
        false,
        '',
      );
    } finally {
      warnSpy.mockRestore();
    }

    expect(detach).toHaveBeenCalledWith('abort', expect.any(Function));
  });

  it('does not re-attach to a stream whose read failed because of the stop', async () => {
    const state = createBaseState({ chatId: 'chat-stop-attach', actionMode: 'agent' });
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(createAbortFailingResponse(abortController.signal));
    armStreamHandlers();

    const run = observe(
      executeStreamWithRetry('hello', 'msg-stop-attach', state, createActions(state), null, abortController, false, ''),
    );
    await eventually(() => expect(mockHandleMessageStream).toHaveBeenCalledTimes(1));

    abortController.abort();
    await eventually(() => expect(run.isSettled()).toBe(true));

    expect(run.error()).toMatchObject({ name: 'AbortError' });
    expect(mockAttachToChat).not.toHaveBeenCalled();
  });

  it('ends the wait before a request retry as soon as the turn is stopped', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const state = createBaseState();
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(new Response('temporary', { status: 503 }));

    try {
      const run = observe(
        executeStreamWithRetry(
          'hello',
          'msg-stop-retry',
          state,
          createActions(state),
          null,
          abortController,
          false,
          '',
        ),
      );
      // The first attempt failed transiently and the loop is backing off before the next one.
      await eventually(() => expect(vi.getTimerCount()).toBe(1));

      abortController.abort();
      // The backoff lasts at least 1.6 s: only the stop can end the turn this early.
      await vi.advanceTimersByTimeAsync(100);

      expect(run.isSettled()).toBe(true);
      expect(run.error()).toMatchObject({ name: 'AbortError' });
      expect(mockCreateMessageRequest).toHaveBeenCalledTimes(1);
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      warnSpy.mockRestore();
    }
  });

  it('ends the wait before an attach retry as soon as the turn is stopped', async () => {
    vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => undefined);
    const errorSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    const state = createBaseState({ chatId: 'chat-stop-attach-wait', actionMode: 'agent' });
    const abortController = new AbortController();
    mockCreateMessageRequest.mockResolvedValue(createInterruptedResponse(STOP_TEST_EVENT));
    armStreamHandlers();
    mockAttachToChat.mockRejectedValue(new Error('attach network down'));

    try {
      const run = observe(
        executeStreamWithRetry(
          'hello',
          'msg-stop-attach-wait',
          state,
          createActions(state),
          null,
          abortController,
          false,
          '',
        ),
      );
      // The interrupted stream's first re-attach failed and the loop is backing off before the next one.
      await eventually(() => expect(vi.getTimerCount()).toBe(1));

      abortController.abort();
      await vi.advanceTimersByTimeAsync(100);

      expect(run.isSettled()).toBe(true);
      expect(run.error()).toMatchObject({ name: 'AbortError' });
      expect(mockAttachToChat).toHaveBeenCalledTimes(1);
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      warnSpy.mockRestore();
      errorSpy.mockRestore();
    }
  });
});
