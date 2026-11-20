/**
 * A compaction's step opens as "compressing" and closes on the phase the stream reports. Every closing phase below is
 * worded from the catalog in each language, never shown as a raw key, and only a compaction that broke is drawn as a
 * warning. The pre-reply gate closes on `completed`, `ineffective`, `skipped` or `failed` and stamps every event with a
 * status; `timeout` and `circuit_open` come from compaction inside a turn, which sends the phase alone, so the phase is
 * what makes them a warning.
 */
import { describe, expect, it, vi } from 'vitest';

import en from '../../../../../../locales/en.json';
import zh from '../../../../../../locales/zh.json';
import { applyStatusProgressStep } from '@/store/chat/messageStream/handlers/statusStreamProgressSteps';
import { getStepVisualState } from '../stepTone';
import { getStepTitle } from '../utils';
import type { StreamCtx } from '@/store/chat/messageStream/streamContext';
import type { ProgressItem } from '@/store/chat/types';

const CATALOGS = { en, zh } as const;

/**
 * The phases a compaction step closes on, the status the stream stamps on the event (none for compaction inside a
 * turn), and whether the step is drawn as a warning.
 */
const CLOSING_PHASES = [
  { phase: 'completed', serverStatus: 'success', warning: false },
  { phase: 'ineffective', serverStatus: 'success', warning: false },
  { phase: 'skipped', serverStatus: 'success', warning: false },
  { phase: 'failed', serverStatus: 'warning', warning: true },
  { phase: 'timeout', serverStatus: undefined, warning: true },
  { phase: 'circuit_open', serverStatus: undefined, warning: true },
] as const;

function messageState() {
  return {
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
}

type MessageState = ReturnType<typeof messageState>;

/** Feed the handler one `context_compaction` status event; compaction inside a turn carries no `status`. */
async function receive(state: MessageState, phase: string, status?: string): Promise<void> {
  const ctx: StreamCtx = {
    data: { type: 'status', messageId: 'msg-1', step_key: 'context_compaction', status, data: { phase } } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: { chatId: 'chat-1', messages: state.messages } as never,
    actions: {
      setLoading: vi.fn(),
      setMessages: vi.fn((updater: (s: MessageState) => void) => updater(state)),
    } as never,
    files: [],
  };
  await applyStatusProgressStep(ctx, 'context_compaction');
}

describe('compaction progress step', () => {
  it('opens as one in-flight step', async () => {
    const state = messageState();

    await receive(state, 'active', 'active');

    expect(state.messages[0].progressSteps).toMatchObject([{ step_key: 'context_compaction', status: 'active' }]);
  });

  describe.each(CLOSING_PHASES)('closing on $phase', ({ phase, serverStatus, warning }) => {
    async function closedStep(): Promise<{ step: ProgressItem; count: number }> {
      const state = messageState();
      await receive(state, 'active', serverStatus === undefined ? undefined : 'active');
      await receive(state, phase, serverStatus);
      return { step: state.messages[0].progressSteps[0], count: state.messages[0].progressSteps.length };
    }

    it('replaces the in-flight step instead of adding a second one', async () => {
      const { step, count } = await closedStep();

      expect(count).toBe(1);
      expect(step.step_key).toBe(`context_compaction_${phase}`);
    });

    it(`is ${warning ? '' : 'not '}drawn as a warning`, async () => {
      const { step } = await closedStep();

      expect(getStepVisualState(step, false).isWarning).toBe(warning);
    });

    it.each(Object.entries(CATALOGS))('is worded from the %s catalog', async (_locale, messages) => {
      const { step } = await closedStep();
      const progressSteps: Record<string, unknown> = messages.progressSteps;
      const copy = progressSteps[`context_compaction_${phase}`];
      const t = (key: string) => (typeof progressSteps[key] === 'string' ? progressSteps[key] : key);

      expect(typeof copy === 'string' && copy.trim() !== '').toBe(true);
      expect(getStepTitle(step, t)).toBe(copy);
    });
  });
});
