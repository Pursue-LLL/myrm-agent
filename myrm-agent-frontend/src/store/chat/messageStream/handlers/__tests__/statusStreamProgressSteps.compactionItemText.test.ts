/**
 * The detail text of a `context_compaction` step comes from what the event carries: the elapsed seconds while
 * compaction runs inside a turn, the tokens saved once it completes. An event that carries no figure leaves the step
 * without a detail instead of showing one the stream never sent.
 */
import { describe, expect, it, vi } from 'vitest';

import { applyStatusProgressStep } from '../statusStreamProgressSteps';
import type { ProgressItem } from '@/store/chat/types';
import type { StreamCtx } from '../../streamContext';

/** Feed the handler one `context_compaction` event and return the detail items of the step it produced. */
async function detailOf(event: Record<string, unknown>): Promise<ProgressItem['items']> {
  const state = {
    messages: [
      {
        content: '',
        messageId: 'msg-1',
        chatId: 'chat-1',
        role: 'assistant' as const,
        progressSteps: [] as ProgressItem[],
        createdAt: new Date(),
      },
    ],
  };
  const ctx: StreamCtx = {
    data: { type: 'status', messageId: 'msg-1', step_key: 'context_compaction', ...event } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: { chatId: 'chat-1', messages: state.messages } as never,
    actions: {
      setLoading: vi.fn(),
      setMessages: vi.fn((updater: (s: typeof state) => void) => updater(state)),
    } as never,
    files: [],
  };
  await applyStatusProgressStep(ctx, 'context_compaction');
  return state.messages[0].progressSteps[0].items;
}

describe('context_compaction detail text', () => {
  describe('elapsed seconds', () => {
    it.each([
      { phase: 'active', seconds: 10, text: '(10s)' },
      { phase: 'active', seconds: 20.3, text: '(20.3s)' },
      { phase: 'timeout', seconds: 90, text: '(90s)' },
    ])('shows $text for the $phase phase when the event reports $seconds seconds', async ({ phase, seconds, text }) => {
      expect(await detailOf({ data: { phase, elapsed_s: seconds } })).toEqual([{ text }]);
    });

    it.each(['active', 'timeout'])('shows no time for the %s phase when the event reports none', async (phase) => {
      expect(await detailOf({ data: { phase } })).toEqual([]);
    });

    it('opens the pre-reply gate step without a time, since the gate does not time its compaction', async () => {
      expect(await detailOf({ status: 'active', data: { phase: 'active' } })).toEqual([]);
    });
  });

  describe('tokens saved', () => {
    it('shows what a completed event reports in its payload', async () => {
      expect(await detailOf({ data: { phase: 'completed', tokens_saved: 4200 } })).toEqual([
        { text: '(Tokens saved: 4200)' },
      ]);
    });

    it.each([{}, { tokens_saved: 0 }])(
      'shows nothing for a completed payload that saved no tokens: %o',
      async (saved) => {
        expect(await detailOf({ data: { phase: 'completed', ...saved } })).toEqual([]);
      },
    );
  });

  it.each(['circuit_open', 'fallback', 'ineffective', 'skipped', 'failed'])(
    'shows no detail for the %s phase',
    async (phase) => {
      expect(await detailOf({ data: { phase } })).toEqual([]);
    },
  );
});
