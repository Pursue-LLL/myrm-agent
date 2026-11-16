/**
 * The two bridge entry points that send a message hand the text to the send pipeline under one contract.
 *
 * Real scenario: `sendChatMessage` and `submitAndObserveTurn` each resolve the baseline user count, the profile and the
 * action-mode flag before calling `submitAndObserveTurn`; when one of them drifts (an option dropped from a single
 * entry point) a CDP E2E run sends something else than the test asked for, without a type error.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { createSendMembers } from '@/components/dev/e2eBridge/members/send';

const pipeline = vi.hoisted(() => ({ submitAndObserveTurn: vi.fn() }));
vi.mock('@/components/dev/e2eBridge/submitAndObserveTurn', () => pipeline);

type EntryPoint = 'sendChatMessage' | 'submitAndObserveTurn';
type Send = (text: string, opts?: Record<string, unknown>) => Promise<unknown>;

const ENTRY_POINTS: EntryPoint[] = ['sendChatMessage', 'submitAndObserveTurn'];
const members = createSendMembers() as unknown as Record<EntryPoint, Send>;
const sealed = { ok: true, mode: 'sendTurnSealed', chatId: 'c-1' };

/** The first four arguments the pipeline received: text, baseline user count, profile, preserve-action-mode flag. */
function pipelineArgs(): unknown[] {
  return pipeline.submitAndObserveTurn.mock.calls[0].slice(0, 4);
}

beforeEach(() => {
  pipeline.submitAndObserveTurn.mockReset().mockResolvedValue(sealed);
  window.__MYRM_E2E_CHAT__ = { turnSnapshot: () => ({ userCount: 7 }) } as unknown as Window['__MYRM_E2E_CHAT__'];
});

afterEach(() => {
  delete window.__MYRM_E2E_CHAT__;
  delete window.__MYRM_E2E_EPH_OPTS__;
});

describe.each(ENTRY_POINTS)('%s', (entry) => {
  it('sends with the defaults when no option is given', async () => {
    await members[entry]('hi');
    expect(pipelineArgs()).toEqual(['hi', 7, 'live', false]);
  });

  it('takes the baseline user count from the options when it is a number, zero included', async () => {
    await members[entry]('hi', { baselineUserCount: 0 });
    expect(pipelineArgs()).toEqual(['hi', 0, 'live', false]);
  });

  it('counts zero users when the bridge has no turn snapshot', async () => {
    window.__MYRM_E2E_CHAT__ = {} as unknown as Window['__MYRM_E2E_CHAT__'];
    await members[entry]('hi');
    expect(pipelineArgs()).toEqual(['hi', 0, 'live', false]);
  });

  it.each([
    ['read', 'read'],
    ['live', 'live'],
    ['anything else', 'live'],
  ])('maps the profile %j to %j', async (profile, expected) => {
    await members[entry]('hi', { profile });
    expect(pipelineArgs()[2]).toBe(expected);
  });

  it.each([
    [true, true],
    ['yes', false],
    [1, false],
    [false, false],
  ])('maps preserveActionMode %j to %j (only `true` preserves)', async (preserveActionMode, expected) => {
    await members[entry]('hi', { preserveActionMode });
    expect(pipelineArgs()[3]).toBe(expected);
  });

  it('returns the pipeline result and keeps it on the bridge', async () => {
    await expect(members[entry]('hi')).resolves.toBe(sealed);
    expect(window.__MYRM_E2E_CHAT__?.lastSubmitResult).toBe(sealed);
  });
});

describe.each(['sendChatMessage', 'submitAndObserveTurn'] as const)('%s ephemeral subagents', (entry) => {
  it('hands ephemeralSubagents to the pipeline', async () => {
    const ephemeralSubagents = { scout: { prompt: 'look around' } };
    await members[entry]('hi', { ephemeralSubagents });
    expect(pipeline.submitAndObserveTurn.mock.calls[0][4]).toBe(ephemeralSubagents);
  });
});

describe('the options record of the ephemeral-subagent diagnostics', () => {
  it('is written by sendChatMessage from the options it received', async () => {
    await members.sendChatMessage('hi', { ephemeralSubagents: { a: {}, b: {} } });
    expect(window.__MYRM_E2E_EPH_OPTS__).toMatchObject({ hasOpts: true, hasEph: true, keys: ['a', 'b'] });
    expect(typeof window.__MYRM_E2E_EPH_OPTS__?.at).toBe('number');

    await members.sendChatMessage('hi');
    expect(window.__MYRM_E2E_EPH_OPTS__).toMatchObject({ hasOpts: false, hasEph: false, keys: [] });
  });

  it('is not written by submitAndObserveTurn', async () => {
    await members.submitAndObserveTurn('hi', { ephemeralSubagents: { a: {} } });
    expect(window.__MYRM_E2E_EPH_OPTS__).toBeUndefined();
  });
});
