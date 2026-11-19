/**
 * The send pipeline of the dev bridge, up to the moment the message is handed to the product: what a send checks,
 * resets and waits for first, and the ephemeral subagents it injects.
 *
 * Real scenario: the Python E2E drivers classify a failed send by `mode` and read `debug` to say why. A change to a
 * guard, a wait or the order of the preparation steps turns a diagnosable failure into an unclassified timeout, or
 * sends a message into a chat that is not ready, without a type error. Stores and progress reads are controllable
 * fakes (`sendTurnFakes.ts`); the action-mode policy and the contract constants are the real ones; time is a fake
 * clock.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import * as pipeline from '@/components/dev/e2eBridge/submitAndObserveTurn';
import { SEND_TURN_OBSERVE_MS, SEND_TURN_REV } from '@/components/dev/e2eBridge/sendTurnContract';
import { bridge, createRun, debugOf, NEVER, restoreWorld, resetWorld, sealable, START, world } from './sendTurnFakes';

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

/** Both 30 s readiness waits plus the observe window: more than any exit needs. */
const run = createRun(pipeline.submitAndObserveTurn, SEND_TURN_OBSERVE_MS + 70_000);

beforeEach(resetWorld);
afterEach(restoreWorld);

describe('before the message is sent', () => {
  it('refuses a message with nothing to send before touching the chat', async () => {
    const result = await run('   ');

    expect(result).toEqual({ ok: false, err: 'empty-message', mode: 'sendTurnEmpty' });
    expect(bridge.abortActiveStream).not.toHaveBeenCalled();
  });

  it.each([
    ['an attachment', { files: [{}] }],
    ['an explicit skill activation', { pendingExplicitSkillActivation: { skill: 's' } }],
  ])('goes on with an empty text when it carries %s', async (_label, patch) => {
    Object.assign(world.chat, patch, { chatId: '' });

    expect((await run('   ')).mode).toBe('sendTurnNoChatId');
  });

  it('prepares the chat in order and dispatches the trimmed text', async () => {
    sealable();
    await run('  hello  ');

    expect(world.chat.setInputMessage).toHaveBeenCalledTimes(1);
    expect(world.chat.setInputMessage).toHaveBeenCalledWith('hello');
    expect(world.chat.sendMessage).toHaveBeenCalledWith('hello', undefined, undefined, undefined, undefined, undefined);
    const order = [
      bridge.abortActiveStream,
      bridge.releaseActiveStreamForApiResume,
      bridge.ensureChatSession,
      world.chat.setInputMessage,
      world.prepareAutomationSend,
      world.approvals.clearAll,
      world.chat.sendMessage,
    ].map((fn) => fn.mock.invocationCallOrder[0]);
    expect(order).toEqual([...order].sort((a, b) => a - b));
  });

  it.each([
    { actionMode: 'agent', preserve: false, session: undefined, prepared: true },
    { actionMode: 'agent', preserve: true, session: { preserveActionMode: true }, prepared: false },
    { actionMode: 'fast', preserve: false, session: { preserveActionMode: true }, prepared: false },
  ])('keeps the action mode: %j', async ({ actionMode, preserve, session, prepared }) => {
    world.chat.actionMode = actionMode;
    sealable();
    await run('hello', { preserve });

    expect(bridge.ensureChatSession).toHaveBeenCalledWith(session);
    expect(world.prepareAutomationSend).toHaveBeenCalledTimes(prepared ? 1 : 0);
  });

  it('ends without a chat id', async () => {
    world.chat.chatId = '  ';

    expect(await run()).toEqual({ ok: false, err: 'no-chat-id', mode: 'sendTurnNoChatId' });
    expect(world.chat.sendMessage).not.toHaveBeenCalled();
  });

  it('refuses fast mode without a configured search service, and only in fast mode', async () => {
    world.chat.actionMode = 'fast';
    world.config.searchServiceConfigs = [{ enabled: true }, { enabled: false }, { enabled: true }];
    world.guardSearchServiceConfigured.mockReturnValue(false);

    expect(await run()).toEqual({
      ok: false,
      err: 'search-not-configured',
      mode: 'sendTurnSearchGuard',
      debug: { actionMode: 'fast', searchCount: 3, enabledCount: 2 },
    });
    expect(world.guardSearchServiceConfigured).toHaveBeenCalledWith(world.config.searchServiceConfigs);

    world.guardSearchServiceConfigured.mockClear();
    world.chat.actionMode = 'agent';
    sealable();
    await run();
    expect(world.guardSearchServiceConfigured).not.toHaveBeenCalled();
  });

  it('ends when the bridge is not ready to send, a missing bridge included', async () => {
    bridge.isSendReady.mockReturnValue(false);
    expect(await run()).toEqual({
      ok: false,
      err: 'send-not-ready',
      mode: 'sendTurnNotReady',
      debug: { providerIds: ['p1'] },
    });

    delete window.__MYRM_E2E_CHAT__;
    expect(await run()).toMatchObject({ ok: false, err: 'send-not-ready', mode: 'sendTurnNotReady' });
  });

  it('releases the request id of the previous send', async () => {
    world.chat.currentSessionMessageId = 'req-1';
    sealable();
    await run();

    expect(world.approvals.unmarkProcessing).toHaveBeenCalledWith('req-1');
    expect(world.chat.clearCurrentSessionMessageId).toHaveBeenCalledTimes(1);

    world.approvals.unmarkProcessing.mockClear();
    world.chat.currentSessionMessageId = '';
    await run();
    expect(world.approvals.unmarkProcessing).not.toHaveBeenCalled();
    expect(world.chat.clearCurrentSessionMessageId).toHaveBeenCalledTimes(2);
  });

  it('waits for the messages to load before it sends', async () => {
    world.chat.isMessagesLoaded = false;
    setTimeout(() => {
      world.chat.isMessagesLoaded = true;
    }, 1_000);
    let sentAt = 0;
    world.chat.sendMessage.mockImplementation(() => {
      sentAt = Date.now();
      return NEVER();
    });
    sealable();
    await run();

    expect(sentAt - START).toBeGreaterThanOrEqual(1_000);
    expect(sentAt - START).toBeLessThan(1_400);
  });

  it.each([{ loading: true }, { abortController: {} }])('waits for a running stream to end: %j', async (busy) => {
    Object.assign(world.chat, busy);
    setTimeout(() => {
      Object.assign(world.chat, { loading: false, abortController: null });
    }, 5_000);
    let sentAt = 0;
    world.chat.sendMessage.mockImplementation(() => {
      sentAt = Date.now();
      return NEVER();
    });
    sealable();
    await run();

    expect(sentAt - START).toBeGreaterThanOrEqual(5_000);
    expect(sentAt - START).toBeLessThan(5_400);
  });

  it.each([{ loading: true }, { abortController: {} }])('reports a chat that stays busy: %j', async (busy) => {
    Object.assign(world.chat, busy);

    expect(await run()).toEqual({
      ok: false,
      err: 'chat-still-busy',
      mode: 'sendTurnBusy',
      debug: { turn: { userCount: 2 }, providerIds: ['p1'] },
    });
    expect(world.chat.sendMessage).not.toHaveBeenCalled();
    expect(world.watchChatStoreTimeline).not.toHaveBeenCalled();
  });

  it('ends in the ARM phase when no model can be selected', async () => {
    world.getModelSelection.mockReturnValue(null);
    const result = await run('hello', { baseline: 3 });

    expect(result).toMatchObject({ ok: false, err: 'model-selection-unavailable', mode: 'sendTurnValidateFailed' });
    expect(result.chatId).toBe('chat-1');
    expect(result.debug).toEqual({
      phase: 'ARM',
      rev: SEND_TURN_REV,
      turn: { userCount: 2 },
      provider: { providerIds: ['p1'] },
      workspace: null,
      chatId: 'chat-1',
      processingIds: ['req-9'],
      approvalQueueLen: 0,
      baselineUsers: 3,
    });
    expect(world.getModelSelection).toHaveBeenCalledWith('agent', null);
    expect(world.chat.sendMessage).not.toHaveBeenCalled();
    expect(world.watchChatStoreTimeline).not.toHaveBeenCalled();
  });

  it.each([
    [new Error('session failed'), 'session failed'],
    ['plain', 'plain'],
  ])('classifies a failure of the session setup, thrown as %j, as unexpected', async (reason, message) => {
    bridge.ensureChatSession.mockRejectedValue(reason);

    expect(await run()).toEqual({
      ok: false,
      err: message,
      mode: 'sendTurnUnexpected',
      debug: { phase: 'SUBMIT', sendGeneration: 4 },
    });
    expect(world.watchChatStoreTimeline).not.toHaveBeenCalled();
  });
});

describe('ephemeral subagents', () => {
  const ephemeral = { scout: { prompt: 'look around' } };

  it('are injected into the send as an agent-config override and reported at the seal', async () => {
    world.chat.agentConfig = { searchDepth: 2 };
    sealable();
    const result = await run('hello', { ephemeral });
    const override = { searchDepth: 2, ephemeralSubagents: ephemeral };

    expect(world.chat.sendMessage).toHaveBeenCalledWith('hello', undefined, undefined, undefined, undefined, override);
    expect(world.getModelSelection).toHaveBeenCalledWith('agent', override);
    expect(window.__MYRM_E2E_EPH_APPLIED__).toEqual({ keys: ['scout'], at: START, forced: false });
    expect(debugOf(result).ephKeys).toEqual(['scout']);
  });

  it('build the override from nothing when the store has no agent config', async () => {
    sealable();
    await run('hello', { ephemeral });

    expect(world.chat.sendMessage.mock.calls[0][5]).toEqual({ ephemeralSubagents: ephemeral });
    expect(window.__MYRM_E2E_EPH_APPLIED__?.forced).toBe(true);
  });

  it.each([
    ['fast mode is forced to agent', { actionMode: 'fast', preserve: false, expected: 'agent', forced: 1 }],
    ['preserve keeps the mode', { actionMode: 'fast', preserve: true, expected: 'fast', forced: 0 }],
  ])('%s', async (_label, { actionMode, preserve, expected, forced }) => {
    world.chat.actionMode = actionMode;
    sealable();
    const result = await run('hello', { ephemeral, preserve });

    expect(world.chat.setActionMode).toHaveBeenCalledTimes(forced);
    expect(debugOf(result).actionModeAtSeal).toBe(expected);
  });

  it.each([undefined, {}])('are ignored when the record is %j', async (empty) => {
    sealable();
    const result = await run('hello', { ephemeral: empty });

    expect(world.chat.sendMessage.mock.calls[0][5]).toBeUndefined();
    expect(world.chat.setActionMode).not.toHaveBeenCalled();
    expect(window.__MYRM_E2E_EPH_APPLIED__).toBeUndefined();
    expect(debugOf(result).ephKeys).toEqual([]);
  });
});
