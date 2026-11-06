/**
 * One-shot stream recovery STATUS steps: the harness fixes the rejected request and re-runs the turn from scratch.
 * Every such step is a progress step, drops the streamed draft and is worded in every locale.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { discardStreamedDraft, clearAssistantDraft } = vi.hoisted(() => ({
  discardStreamedDraft: vi.fn(),
  clearAssistantDraft: vi.fn(),
}));

vi.mock('../handlerDeps', () => ({
  findAssistantMessageIndex: vi.fn(() => 0),
  ensureAssistantStreamMessage: vi.fn(() => 0),
  parseArchiveRestoreBlockPayload: vi.fn(),
  parseArchiveRestoreResultPayload: vi.fn(),
  buildArchiveRestoreActions: vi.fn(() => []),
  discardStreamedDraft,
  clearAssistantDraft,
}));

import de from '../../../../../../locales/de.json';
import en from '../../../../../../locales/en.json';
import ja from '../../../../../../locales/ja.json';
import ko from '../../../../../../locales/ko.json';
import zhTW from '../../../../../../locales/zh-TW.json';
import zh from '../../../../../../locales/zh.json';
import { getStepTitle } from '@/components/features/message-box/progress-steps/utils';
import { applyStatusProgressStep, isStatusProgressStep } from '../statusStreamProgressSteps';
import type { ProgressItem } from '@/store/chat/types';
import type { StreamCtx } from '../../streamContext';

/** Every step key the harness's one-shot recovery handlers emit with `restart: true`. */
const ONE_SHOT_RECOVERY_STEPS = [
  'thinking_signature_recovery',
  'reasoning_mandatory_recovery',
  'tool_history_recovery',
  'image_shrink_recovery',
  'vision_fallback_recovery',
  'media_rejected_recovery',
  'allowed_tools_rejected_recovery',
  'long_context_tier_recovery',
] as const;

function makeMessagesState() {
  return {
    messages: [
      {
        content: 'a drafted answer',
        messageId: 'msg-1',
        chatId: 'c1',
        role: 'assistant' as const,
        progressSteps: [] as ProgressItem[],
        createdAt: new Date(),
      },
    ],
  };
}

type MessagesState = ReturnType<typeof makeMessagesState>;

/** What the harness sends: the step key and the restart signal, no wording. */
function makeCtx(state: MessagesState, stepKey: string): StreamCtx {
  const setMessages = vi.fn((updater: (s: MessagesState) => void) => {
    updater(state);
  });
  return {
    data: { type: 'status', step_key: stepKey, tool_name: null, messageId: 'msg-1', restart: true } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: {} as never,
    actions: { setLoading: vi.fn(), setMessages: setMessages as never } as never,
    files: [],
  };
}

describe.each(ONE_SHOT_RECOVERY_STEPS)('applyStatusProgressStep %s', (stepKey) => {
  beforeEach(() => {
    discardStreamedDraft.mockClear();
    clearAssistantDraft.mockClear();
  });

  it('recognizes the step as a progress step', () => {
    expect(isStatusProgressStep(stepKey)).toBe(true);
  });

  it('drops the streamed draft, in the stream buffer and on the message', async () => {
    const state = makeMessagesState();

    await applyStatusProgressStep(makeCtx(state, stepKey), stepKey);

    expect(discardStreamedDraft).toHaveBeenCalledTimes(1);
    expect(clearAssistantDraft).toHaveBeenCalledWith(state.messages[0]);
  });

  it('records the step on the message', async () => {
    const state = makeMessagesState();

    await applyStatusProgressStep(makeCtx(state, stepKey), stepKey);

    expect(state.messages[0].progressSteps.map((step) => step.step_key)).toEqual([stepKey]);
  });
});

describe('one-shot recovery step titles', () => {
  const CATALOGS = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;

  describe.each(Object.entries(CATALOGS))('%s', (_locale, messages) => {
    const progressSteps: Record<string, unknown> = messages.progressSteps;
    const t = (key: string) => (typeof progressSteps[key] === 'string' ? progressSteps[key] : key);

    it.each(ONE_SHOT_RECOVERY_STEPS)('titles %s from the catalog, not as the raw key', (stepKey) => {
      const step: ProgressItem = { step_key: stepKey, items: [], status: 'warning' };

      const title = getStepTitle(step, t);

      expect(title).toBe(progressSteps[stepKey]);
      expect(title).not.toBe(stepKey);
      expect(title.trim()).not.toBe('');
    });
  });
});
