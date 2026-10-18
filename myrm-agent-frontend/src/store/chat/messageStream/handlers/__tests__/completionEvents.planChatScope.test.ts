/**
 * The plan panel describes the plan of the chat the user has open.
 *
 * Real scenario: a goal turn runs in chat A while the user reads chat B. A's MESSAGE_END must not wipe the plan
 * steps B is showing. The terminal event clears the plan only of the chat that owns the ending turn.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/services/notification', () => ({
  notificationService: { notify: vi.fn() },
}));

vi.mock('@/lib/utils/completionSound', () => ({
  playCompletionSound: vi.fn(() => false),
}));

vi.mock('@/components/features/companion/sprite/petSurfaceAwayCompletion', () => ({
  dispatchPetSurfaceAwayCompletion: vi.fn(),
}));

vi.mock('@/lib/progression/tryMarkMilestone', () => ({
  tryMarkMilestone: vi.fn(),
}));

vi.mock('@/lib/inspector/releaseTurnInspectorControls', () => ({
  releaseTurnInspectorControls: vi.fn(() => Promise.resolve()),
}));

vi.mock('@/services/chat', () => ({
  getChatDetail: vi.fn(async () => ({ chat: {} })),
}));

vi.mock('@/lib/api', () => ({
  fetchWithTimeout: vi.fn(async () => ({ ok: true, json: async () => ({ plan: null }) })),
}));

import { usePlanStore } from '@/store/chat/goals/usePlanStore';
import useChatStore from '@/store/useChatStore';
import type { StreamHandlerState } from '../../types';
import { completionEvents } from '../completionEvents';
import type { StreamCtx } from '../../streamContext';

const OPEN_CHAT = 'chat-open';
const BACKGROUND_CHAT = 'chat-background';

function makeActivePlan() {
  return {
    goal: 'Plan of the open chat',
    reasoning: '',
    steps: [
      { step_id: 'a', description: 'Step A', expected_output: '', status: 'in_progress' as const, dependencies: [] },
      { step_id: 'b', description: 'Step B', expected_output: '', status: 'pending' as const, dependencies: [] },
    ],
  };
}

/** The stream of `streamChatId`, delivering MESSAGE_END. */
function streamOf(streamChatId: string): StreamCtx {
  const state: StreamHandlerState = {
    chatId: streamChatId,
    messages: [{ messageId: 'msg-1', chatId: streamChatId, role: 'assistant', content: '', createdAt: new Date() }],
    messageAppeared: false,
    loading: true,
    scheduler: {} as StreamHandlerState['scheduler'],
  };
  return {
    data: { type: 'message_end', messageId: 'msg-1' } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: 'done',
    state,
    actions: {
      setMessages: vi.fn((updater: (s: Record<string, unknown>) => void) =>
        updater({
          messages: [
            { messageId: 'msg-1', chatId: streamChatId, role: 'assistant', content: '', createdAt: new Date() },
          ],
          loading: true,
          messageAppeared: false,
        }),
      ),
      setLoading: vi.fn(),
      setMessageAppeared: vi.fn(),
      clearActiveStream: vi.fn(),
      _processSuggestions: vi.fn(async () => undefined),
      scheduleAutoSave: vi.fn(),
    } as never,
    files: [],
  };
}

describe('completionEvents plan scope', () => {
  beforeEach(() => {
    usePlanStore.setState({ plan: makeActivePlan(), isLoading: false });
    useChatStore.setState({ chatId: OPEN_CHAT });
  });

  it('clears the plan when the turn of the open chat ends', async () => {
    await completionEvents(streamOf(OPEN_CHAT));
    await vi.dynamicImportSettled();

    expect(usePlanStore.getState().plan).toBeNull();
  });

  it('leaves the plan of the open chat alone when a background turn ends', async () => {
    await completionEvents(streamOf(BACKGROUND_CHAT));
    await vi.dynamicImportSettled();

    expect(usePlanStore.getState().plan).not.toBeNull();
    expect(usePlanStore.getState().plan?.goal).toBe('Plan of the open chat');
  });
});
