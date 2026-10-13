/**
 * sendMessage reports an undelivered turn differently for a fresh send and for a resume.
 *
 * Real scenario: the user answers an approval card after the session has expired and the request is refused, or
 * the connection drops before the server replies. A fresh send resolves `false` so its caller can hand the typed
 * text back; a resume carries no text to hand back and its callers roll the card back from a catch block, like
 * every other resume route. An undelivered resume that only resolved `false` would leave the card marked answered
 * while the agent never continued.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

import useChatStore from '@/store/useChatStore';

const pipeline = vi.hoisted(() => ({ sendMessage: vi.fn<() => Promise<boolean>>() }));

vi.mock('@/store/chat/messageRequest', () => pipeline);

const send = (resumeValue?: unknown) => useChatStore.getState().sendMessage('', 'msg-1', undefined, resumeValue);

beforeEach(() => {
  pipeline.sendMessage.mockReset();
});

describe('sendMessage undelivered-turn contract', () => {
  it('resolves false for an undelivered fresh send', async () => {
    pipeline.sendMessage.mockResolvedValue(false);

    await expect(send()).resolves.toBe(false);
  });

  it('resolves true for a dispatched fresh send', async () => {
    pipeline.sendMessage.mockResolvedValue(true);

    await expect(send()).resolves.toBe(true);
  });

  it.each([
    ['an answer', { answer: 'yes' }],
    ['an empty skip payload', {}],
  ])('rejects an undelivered resume carrying %s', async (_label, resumeValue) => {
    pipeline.sendMessage.mockResolvedValue(false);

    await expect(send(resumeValue)).rejects.toThrow('not delivered');
  });

  it('resolves true for a dispatched resume', async () => {
    pipeline.sendMessage.mockResolvedValue(true);

    await expect(send({ granted: true })).resolves.toBe(true);
  });
});
