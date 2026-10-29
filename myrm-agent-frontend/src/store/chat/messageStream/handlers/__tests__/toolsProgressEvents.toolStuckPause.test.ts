/**
 * A loop guard pause (`approval_required` with `action_type: 'tool_stuck'`) is one localized, continuable step —
 * not the generic "approval required" step with a hard-coded sentence.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { showI18nToast } = vi.hoisted(() => ({ showI18nToast: vi.fn() }));

vi.mock('@/services/i18nToastService', () => ({ showI18nToast }));

vi.mock('../handlerDeps', () => ({
  AgentEventType: { APPROVAL_REQUIRED: 'approval_required' },
  findAssistantMessageIndex: vi.fn(() => 0),
}));

import { toolsProgressEvents } from '../toolsProgressEvents';
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

function makeCtx(payload: Record<string, unknown>, state: MessagesState): StreamCtx {
  return {
    data: { type: 'approval_required', messageId: 'msg-1', data: payload } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: { chatId: 'c1', messages: state.messages } as never,
    actions: {
      setLoading: vi.fn(),
      setMessages: vi.fn((updater: (s: MessagesState) => void) => updater(state)),
    } as never,
    files: [],
  };
}

/** What the harness sends when the loop guard pauses the run. */
const TOOL_STUCK_PAYLOAD = {
  action_type: 'tool_stuck',
  tool_name: 'web_fetch_tool',
  tool_call_id: 'call-1',
  error_message: 'TOOL_STUCK_EXCEPTION: Tool failed 3 times in a row with identical arguments.',
};

describe('toolsProgressEvents tool_stuck pause', () => {
  beforeEach(() => {
    showI18nToast.mockClear();
  });

  it('shows one error step worded by the catalog, without the tool row or the raw exception text', async () => {
    const state = makeMessagesState();
    const ctx = makeCtx(TOOL_STUCK_PAYLOAD, state);

    await toolsProgressEvents(ctx);

    expect(state.messages[0].progressSteps).toEqual([{ step_key: 'tool_stuck_paused', items: [], status: 'error' }]);
    expect(ctx.actions.setLoading).toHaveBeenCalledWith(false);
  });

  it('also tells the user right away, since the step sits in the collapsed task list', async () => {
    await toolsProgressEvents(makeCtx(TOOL_STUCK_PAYLOAD, makeMessagesState()));

    expect(showI18nToast).toHaveBeenCalledTimes(1);
    expect(showI18nToast).toHaveBeenCalledWith('progressSteps.tool_stuck_paused', undefined, {
      type: 'warning',
      duration: 8000,
    });
  });

  it('keeps the message of any other approval_required pause', async () => {
    const state = makeMessagesState();

    await toolsProgressEvents(makeCtx({ type: 'manual', message: 'Needs a human' }, state));

    expect(state.messages[0].progressSteps).toEqual([
      { step_key: 'approval_required', items: [{ text: 'Needs a human' }], status: 'error' },
    ]);
    expect(showI18nToast).not.toHaveBeenCalled();
  });
});
