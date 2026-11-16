/**
 * The send pipeline of the dev bridge, from the dispatch of the message on: when a send seals, every other way it
 * ends, and the evidence each result reports.
 *
 * Real scenario: the Python E2E drivers classify a failed send by `mode` and read `debug` (phase, counters, trace). A
 * change to an exit condition, a mode or a debug key turns a diagnosable failure into an unclassified timeout, or
 * seals a send whose user row never reached the API, without a type error. Stores and progress reads are
 * controllable fakes (`sendTurnFakes.ts`); the turn trace and the contract constants are the real ones; time is a
 * fake clock.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as pipeline from '@/components/dev/e2eBridge/submitAndObserveTurn';
import { SEND_TURN_OBSERVE_MS, SEND_TURN_REV } from '@/components/dev/e2eBridge/sendTurnContract';
import {
  createRun,
  debugOf,
  DIAGNOSTIC_KEYS,
  EVIDENCE_KEYS,
  keySet,
  keysOf,
  NEVER,
  OBSERVED_KEYS,
  restoreWorld,
  resetWorld,
  type Result,
  sealable,
  watch,
  world,
} from './sendTurnFakes';

vi.mock('@/store/useChatStore', async () => (await import('./sendTurnFakes')).mocks.chatStore);
vi.mock('@/store/useToolApprovalStore', async () => (await import('./sendTurnFakes')).mocks.approvalStore);
vi.mock('@/store/useConfigStore', async () => (await import('./sendTurnFakes')).mocks.configStore);
vi.mock('@/store/config/searchService', async () => (await import('./sendTurnFakes')).mocks.searchService);
vi.mock('@/store/chat/messageRequest', async () => (await import('./sendTurnFakes')).mocks.messageRequest);
vi.mock('@/components/dev/e2eBridge/turnProgress', async () => (await import('./sendTurnFakes')).mocks.turnProgress);
vi.mock(
  '@/components/dev/e2eBridge/e2eStoreTimelineWatcher',
  async () => (await import('./sendTurnFakes')).mocks.storeTimelineWatcher,
);
vi.mock('@/components/dev/e2eBridge/hostEnv', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/components/dev/e2eBridge/hostEnv')>()),
  prepareAutomationSend: (await import('./sendTurnFakes')).world.prepareAutomationSend,
}));

/** The observe window plus the readiness waits: more than any exit needs. */
const run = createRun(pipeline.submitAndObserveTurn, SEND_TURN_OBSERVE_MS + 70_000);

type Trace = { events: Array<{ type: string }>; settle: { outcome: string } | null };
const traceOf = (result: Result): Trace => debugOf(result).turnTrace as Trace;

beforeEach(resetWorld);
afterEach(restoreWorld);

describe('a send that is observed', () => {
  it('seals once the UI shows progress and the API holds the user row', async () => {
    sealable();
    const result = await run('hello');

    expect(result).toMatchObject({ ok: true, chatId: 'chat-1', mode: 'sendTurnSealed' });
    expect(keysOf(result)).toEqual(
      keySet(EVIDENCE_KEYS, OBSERVED_KEYS, ['rev', 'chatIdBeforeSend', 'ephKeys', 'actionModeAtSeal']),
    );
    expect(result.debug).toMatchObject({
      phase: 'SEAL',
      profile: 'live',
      rev: SEND_TURN_REV,
      sendGeneration: 4,
      apiUsers: 1,
      apiPoll: { polls: 1, notFound: 0, failures: 0, lastFailure: null, slowestMs: 0 },
      storeTimeline: { marker: 'store-timeline' },
      userCount: 1,
      streaming: true,
      baselineUsers: 0,
      chatIdBeforeSend: undefined,
      actionModeAtSeal: 'agent',
    });
    expect(watch.stop).toHaveBeenCalledTimes(1);
  });

  it('reports the chat id of the send when a new chat replaced the one before it', async () => {
    sealable();
    world.chat.sendMessage.mockImplementation(() => {
      world.chat.chatId = 'chat-2';
      return NEVER();
    });
    const result = await run();

    expect(result).toMatchObject({ ok: true, chatId: 'chat-2' });
    expect(debugOf(result).chatIdBeforeSend).toBe('chat-1');
    expect(world.pollApiUserMessages).toHaveBeenCalledWith('chat-2');
  });

  it('keeps observing while the chat has no id', async () => {
    sealable();
    world.chat.sendMessage.mockImplementation(() => {
      world.chat.chatId = '';
      setTimeout(() => {
        world.chat.chatId = 'chat-7';
      }, 600);
      return NEVER();
    });
    const result = await run();

    expect(result).toMatchObject({ ok: true, chatId: 'chat-7' });
    expect(world.pollApiUserMessages.mock.calls.map(([id]) => id)).toEqual(['chat-7']);
  });

  it('counts the polls, the 404s, the failures and the slowest answer', async () => {
    world.progress.value = { userCount: 1, streaming: true, uiProgress: true };
    const answers = [
      { delay: 10, poll: { users: 0, notFound: true, failure: null } },
      { delay: 70, poll: { users: 0, notFound: false, failure: 'http-500' } },
      { delay: 20, poll: { users: 1, notFound: false, failure: null } },
    ];
    world.pollApiUserMessages.mockImplementation(async () => {
      const { delay, poll } = answers.shift() ?? { delay: 0, poll: { users: 1, notFound: false, failure: null } };
      await new Promise((resolve) => setTimeout(resolve, delay));
      return poll;
    });
    const result = await run();

    expect(result.mode).toBe('sendTurnSealed');
    expect(debugOf(result).apiPoll).toEqual({
      polls: 3,
      notFound: 1,
      failures: 1,
      lastFailure: 'http-500',
      slowestMs: 70,
    });
  });

  it('ends with an observe timeout after the observe window, polling every 250 ms', async () => {
    world.progress.value = { userCount: 1, streaming: true, uiProgress: true };
    world.chat.sendMessage.mockImplementation(() => {
      world.chat.chatId = 'chat-2';
      return NEVER();
    });
    const result = await run();

    expect(result).toMatchObject({ ok: false, err: 'send-turn-observe-timeout', mode: 'sendTurnObserveTimeout' });
    expect(result.chatId).toBe('chat-2');
    expect(keysOf(result)).toEqual(keySet(DIAGNOSTIC_KEYS, EVIDENCE_KEYS, OBSERVED_KEYS, ['sendSettledEmpty']));
    expect(result.debug).toMatchObject({
      phase: 'OBSERVE',
      apiUsers: 0,
      userCount: 1,
      streaming: true,
      sendSettledEmpty: false,
      chatId: 'chat-2',
    });
    expect((debugOf(result).apiPoll as { polls: number }).polls).toBe(SEND_TURN_OBSERVE_MS / 250 + 1);
    expect(watch.stop).toHaveBeenCalledTimes(1);
  });

  it('stops when the page session was reset during the send', async () => {
    world.chat.sendMessage.mockImplementation(() => {
      world.generation.value = 5;
      return NEVER();
    });

    expect(await run()).toEqual({
      ok: false,
      err: 'session-reset-during-submit',
      mode: 'sendTurnGenerationMismatch',
      chatId: 'chat-1',
      debug: { phase: 'OBSERVE', sendGeneration: 4, currentGeneration: 5 },
    });
    expect(watch.stop).toHaveBeenCalledTimes(1);
  });
});

describe.each(['live', 'read'] as const)('the exits of the %s profile', (profile) => {
  it.each([
    { api: 1, ui: true, err: undefined, mode: 'sendTurnSealed', elapsedMs: undefined },
    { api: 0, ui: true, err: 'send-turn-observe-timeout', mode: 'sendTurnObserveTimeout', elapsedMs: undefined },
    { api: 1, ui: false, err: 'send-turn-observe-timeout', mode: 'sendTurnObserveTimeout', elapsedMs: undefined },
    { api: 0, ui: false, err: 'send-kickoff-no-progress', mode: 'sendTurnSubmitNoOp', elapsedMs: 3_000 },
  ])('api rows $api, ui progress $ui: $mode', async ({ api, ui, err, mode, elapsedMs }) => {
    world.api.users = api;
    world.progress.value = { userCount: ui ? 1 : 0, streaming: ui, uiProgress: ui };
    const result = await run('hello', { profile });

    expect(result.mode).toBe(mode);
    expect(result.err).toBe(err);
    expect(debugOf(result).profile).toBe(profile);
    if (elapsedMs !== undefined) {
      expect(result.debug).toMatchObject({ phase: 'OBSERVE', elapsedMs, sendSettledEmpty: false });
      expect(keysOf(result)).toEqual(
        keySet(DIAGNOSTIC_KEYS, EVIDENCE_KEYS, OBSERVED_KEYS, ['elapsedMs', 'sendSettledEmpty']),
      );
    }
  });

  it.each([
    { userCount: 1, streaming: false },
    { userCount: 0, streaming: true },
  ])('seals on either kind of progress ($userCount user rows, streaming $streaming)', async (progress) => {
    world.api.users = 1;
    world.progress.value = { ...progress, uiProgress: true };
    const result = await run('hello', { profile });

    expect(result.mode).toBe('sendTurnSealed');
    expect(result.debug).toMatchObject(progress);
  });
});

describe('a send promise that ends', () => {
  it.each([
    [true, 'resolved'],
    [false, 'resolved-undispatched'],
  ])('with %j before any progress ends as a no-op after 1.5 s (trace: %s)', async (dispatched, outcome) => {
    world.chat.sendMessage.mockImplementation(() => Promise.resolve(dispatched));
    const result = await run('hello', { baseline: 2 });

    expect(result).toMatchObject({
      ok: false,
      err: 'send-message-settled-without-progress',
      mode: 'sendTurnSubmitNoOp',
      chatId: 'chat-1',
    });
    expect(result.debug).toMatchObject({
      phase: 'SUBMIT',
      profile: 'live',
      sendGeneration: 4,
      apiUsers: 0,
      userCount: 0,
      streaming: false,
      baselineUsers: 2,
      elapsedMs: 1_500,
      rev: SEND_TURN_REV,
    });
    expect(traceOf(result).settle?.outcome).toBe(outcome);
    expect(keysOf(result)).toEqual(keySet(DIAGNOSTIC_KEYS, EVIDENCE_KEYS, OBSERVED_KEYS, ['elapsedMs']));
    expect(watch.stop).toHaveBeenCalledTimes(1);
  });

  it('is judged on the chat the send ended up in', async () => {
    world.chat.sendMessage.mockImplementation(() => {
      world.chat.chatId = 'chat-2';
      return Promise.resolve(true);
    });
    const result = await run();

    expect(result).toMatchObject({ err: 'send-message-settled-without-progress', chatId: 'chat-2' });
    expect(world.resolveE2eTurnProgress.mock.calls.map(([id]) => id)).not.toContain('chat-1');
  });

  it('with progress already on screen is not treated as empty', async () => {
    world.chat.sendMessage.mockImplementation(() => Promise.resolve(true));
    world.progress.value = { userCount: 1, streaming: true, uiProgress: true };
    setTimeout(() => {
      world.api.users = 1;
    }, 2_000);
    const result = await run();

    expect(result).toMatchObject({ ok: true, mode: 'sendTurnSealed' });
    expect(debugOf(result).apiUsers).toBe(1);
  });

  it.each([
    [new Error('boom'), 'boom'],
    ['plain', 'plain'],
  ])('by rejecting with %j ends as a submit error', async (reason, message) => {
    world.chat.sendMessage.mockImplementation(() => Promise.reject(reason));
    const result = await run();

    expect(result).toMatchObject({ ok: false, err: message, mode: 'sendTurnSubmitError', chatId: 'chat-1' });
    expect(result.debug).toMatchObject({
      phase: 'SUBMIT',
      sendGeneration: 4,
      storeTimeline: { marker: 'store-timeline' },
    });
    expect(traceOf(result).settle?.outcome).toBe(`rejected:${message}`);
    expect(keysOf(result)).toEqual(keySet(DIAGNOSTIC_KEYS, EVIDENCE_KEYS, ['phase', 'sendGeneration']));
    expect(watch.stop).toHaveBeenCalledTimes(1);
  });

  it('by throwing at the call still stops the store watch', async () => {
    world.chat.sendMessage.mockImplementation(() => {
      throw new Error('sync failure');
    });

    expect(await run()).toMatchObject({ ok: false, err: 'sync failure', mode: 'sendTurnUnexpected' });
    expect(watch.stop).toHaveBeenCalledTimes(1);
  });
});

describe('the trace of the latest send', () => {
  it('ignores events before the first send', () => {
    expect(() => pipeline.recordActiveTurnEvent('message_start')).not.toThrow();
  });

  it('receives the events recorded from the call of sendMessage on, in order', async () => {
    sealable();
    world.chat.sendMessage.mockImplementation(() => {
      pipeline.recordActiveTurnEvent('routing_decision');
      return NEVER();
    });
    world.resolveE2eTurnProgress.mockImplementation(() => {
      pipeline.recordActiveTurnEvent('message_end');
      return world.progress.value;
    });
    const trace = traceOf(await run());

    expect(trace.events.map((event) => event.type)).toEqual(['routing_decision', 'message_end']);
    expect(trace.settle).toBeNull();
  });

  it('belongs to the newest send only', async () => {
    sealable();
    await run();
    pipeline.recordActiveTurnEvent('late-event');

    expect(traceOf(await run()).events).toEqual([]);
  });
});
