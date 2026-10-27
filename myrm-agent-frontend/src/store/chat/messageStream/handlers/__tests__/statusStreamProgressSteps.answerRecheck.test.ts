/**
 * answer_recheck STATUS step — the harness held a drafted answer back and asks the model again.
 * The step carries the stream's restart signal: the streamed draft is dropped, and the step is worded in every locale.
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
import { getStepCategory } from '@/components/features/message-box/progress-steps/toolIcons';
import { applyStatusProgressStep, isStatusProgressStep } from '../statusStreamProgressSteps';
import type { ProgressItem } from '@/store/chat/types';
import type { StreamCtx } from '../../streamContext';

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
function makeCtx(state: MessagesState): StreamCtx {
  const setMessages = vi.fn((updater: (s: MessagesState) => void) => {
    updater(state);
  });
  return {
    data: {
      type: 'status',
      step_key: 'answer_recheck',
      messageId: 'msg-1',
      status: 'warning',
      restart: true,
      data: { step_key: 'answer_recheck', status: 'warning', restart: true },
    } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: {} as never,
    actions: { setLoading: vi.fn(), setMessages: setMessages as never } as never,
    files: [],
  };
}

describe('applyStatusProgressStep answer_recheck', () => {
  beforeEach(() => {
    discardStreamedDraft.mockClear();
    clearAssistantDraft.mockClear();
  });

  it('recognizes the step as a progress step', () => {
    expect(isStatusProgressStep('answer_recheck')).toBe(true);
  });

  it('drops the streamed draft, in the stream buffer and on the message', async () => {
    const state = makeMessagesState();

    await applyStatusProgressStep(makeCtx(state), 'answer_recheck');

    expect(discardStreamedDraft).toHaveBeenCalledTimes(1);
    expect(clearAssistantDraft).toHaveBeenCalledWith(state.messages[0]);
  });

  it('shows one warning step however many drafts are held back, without a tool or a text body', async () => {
    const state = makeMessagesState();

    await applyStatusProgressStep(makeCtx(state), 'answer_recheck');
    await applyStatusProgressStep(makeCtx(state), 'answer_recheck');
    await applyStatusProgressStep(makeCtx(state), 'answer_recheck');

    expect(state.messages[0].progressSteps).toHaveLength(1);
    const [step] = state.messages[0].progressSteps;
    expect(step.step_key).toBe('answer_recheck');
    expect(step.status).toBe('warning');
    expect(step.tool_name).toBeUndefined();
    expect(step.items).toEqual([]);
  });

  it('groups the step with the thinking steps', () => {
    expect(getStepCategory('answer_recheck', null)).toBe('thinking');
  });
});

describe('answer_recheck step title', () => {
  const CATALOGS = { en, zh, 'zh-TW': zhTW, ja, ko, de } as const;

  describe.each(Object.entries(CATALOGS))('%s', (_locale, messages) => {
    const progressSteps: Record<string, unknown> = messages.progressSteps;
    const copy = typeof progressSteps.answer_recheck === 'string' ? progressSteps.answer_recheck : '';
    const t = (key: string) => (typeof progressSteps[key] === 'string' ? progressSteps[key] : key);

    it('titles the step from the catalog, not as the raw key', () => {
      const step: ProgressItem = { step_key: 'answer_recheck', items: [], status: 'warning' };

      const title = getStepTitle(step, t);

      expect(title).toBe(copy);
      expect(title).not.toBe('answer_recheck');
      expect(title.trim()).not.toBe('');
    });
  });
});
