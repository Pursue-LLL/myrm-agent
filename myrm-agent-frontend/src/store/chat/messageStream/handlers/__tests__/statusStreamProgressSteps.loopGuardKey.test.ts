/**
 * loop_guard_warn / loop_guard_break STATUS steps — the harness names the loop kind, the UI words it.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { showI18nToast } = vi.hoisted(() => ({ showI18nToast: vi.fn() }));

vi.mock('@/services/i18nToastService', () => ({ showI18nToast }));

vi.mock('../handlerDeps', () => ({
  findAssistantMessageIndex: vi.fn(() => 0),
  ensureAssistantStreamMessage: vi.fn(() => 0),
  parseArchiveRestoreBlockPayload: vi.fn(),
  parseArchiveRestoreResultPayload: vi.fn(),
  buildArchiveRestoreActions: vi.fn(() => []),
  discardStreamedDraft: vi.fn(),
  clearAssistantDraft: vi.fn(),
}));

import { applyStatusProgressStep, isStatusProgressStep } from '../statusStreamProgressSteps';
import type { ProgressItem } from '@/store/chat/types';
import type { StreamCtx } from '../../streamContext';

function makeMessagesState() {
  return {
    messages: [
      {
        content: '',
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

/** What the harness sends: the loop kind and the tool the guard fired on, no wording. */
function makeCtx(stepKey: string, loopKind: string | undefined, state: MessagesState): StreamCtx {
  const setMessages = vi.fn((updater: (s: MessagesState) => void) => {
    updater(state);
  });
  return {
    data: {
      type: 'status',
      step_key: stepKey,
      messageId: 'msg-1',
      status: stepKey === 'loop_guard_break' ? 'error' : 'warning',
      tool_name: 'web_fetch_tool',
      data: { step_key: stepKey, tool_name: 'web_fetch_tool', loop_kind: loopKind },
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

describe('applyStatusProgressStep loop guard steps', () => {
  beforeEach(() => {
    showI18nToast.mockClear();
  });

  it('recognizes both loop guard steps as progress steps', () => {
    expect(isStatusProgressStep('loop_guard_warn')).toBe(true);
    expect(isStatusProgressStep('loop_guard_break')).toBe(true);
  });

  it.each([
    ['iteration_budget', 'loop_guard_warn_budget'],
    ['repetition', 'loop_guard_warn_repeat'],
    ['ping_pong', 'loop_guard_warn_repeat'],
    ['no_progress', 'loop_guard_warn_repeat'],
    ['divergence', 'loop_guard_warn'],
    ['output_diminishing', 'loop_guard_warn'],
    ['consecutive_failures', 'loop_guard_warn'],
    ['error_signature', 'loop_guard_warn'],
    [undefined, 'loop_guard_warn'],
  ])('shows a %s warning under %s', async (loopKind, expectedKey) => {
    const state = makeMessagesState();

    await applyStatusProgressStep(makeCtx('loop_guard_warn', loopKind, state), 'loop_guard_warn');

    expect(state.messages[0].progressSteps.map((step) => step.step_key)).toEqual([expectedKey]);
  });

  it('shows a warning as a warning of its own, not as the tool it fired on, and without a text body', async () => {
    const state = makeMessagesState();

    await applyStatusProgressStep(makeCtx('loop_guard_warn', 'repetition', state), 'loop_guard_warn');

    const [step] = state.messages[0].progressSteps;
    expect(step.tool_name).toBeUndefined();
    expect(step.items).toEqual([]);
    expect(step.status).toBe('warning');
  });

  it('keeps one step per kind of warning however often it repeats', async () => {
    const state = makeMessagesState();

    await applyStatusProgressStep(makeCtx('loop_guard_warn', 'repetition', state), 'loop_guard_warn');
    await applyStatusProgressStep(makeCtx('loop_guard_warn', 'ping_pong', state), 'loop_guard_warn');
    await applyStatusProgressStep(makeCtx('loop_guard_warn', 'iteration_budget', state), 'loop_guard_warn');
    await applyStatusProgressStep(makeCtx('loop_guard_warn', 'iteration_budget', state), 'loop_guard_warn');

    expect(state.messages[0].progressSteps.map((step) => step.step_key)).toEqual([
      'loop_guard_warn_repeat',
      'loop_guard_warn_budget',
    ]);
    expect(showI18nToast).not.toHaveBeenCalled();
  });

  it('shows a stop as one error step and tells the user in their language', async () => {
    const state = makeMessagesState();

    await applyStatusProgressStep(makeCtx('loop_guard_break', 'repetition', state), 'loop_guard_break');

    const [step] = state.messages[0].progressSteps;
    expect(step.step_key).toBe('loop_guard_break');
    expect(step.status).toBe('error');
    expect(step.tool_name).toBeUndefined();
    expect(step.items).toEqual([]);
    expect(showI18nToast).toHaveBeenCalledTimes(1);
    expect(showI18nToast).toHaveBeenCalledWith('progressSteps.loop_guard_break_toast', undefined, {
      type: 'error',
      duration: 8000,
    });
  });

  it('leaves the tool of other steps alone', async () => {
    const state = makeMessagesState();
    const ctx = makeCtx('transient_retry', undefined, state);

    await applyStatusProgressStep(ctx, 'transient_retry');

    expect(state.messages[0].progressSteps[0].tool_name).toBe('web_fetch_tool');
  });
});
