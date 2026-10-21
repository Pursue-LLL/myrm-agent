/**
 * An approval card belongs to the turn that raised it.
 *
 * Real scenario: chat A pauses for approval while the user is reading chat B, whose mode differs. The card must be
 * attributed to A and to A's mode, so answering it resumes A's turn and the mode-specific model selection is right.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/approval/approvalAlertService', () => ({
  notifyIdleApproval: vi.fn(),
}));

vi.mock('@/lib/utils/toast', () => ({
  toast: { error: vi.fn(), warning: vi.fn(), success: vi.fn() },
}));

import useToolApprovalStore from '@/store/useToolApprovalStore';
import useChatStore from '@/store/useChatStore';
import type { StreamHandlerState } from '../../types';
import { toolsProgressEvents } from '../toolsProgressEvents';
import type { StreamCtx } from '../../streamContext';

const OPEN_CHAT = 'chat-open';
const BACKGROUND_CHAT = 'chat-background';

function approvalPayload(action: string) {
  return {
    actionRequests: [{ action, args: { command: action }, description: `run ${action}` }],
    reviewConfigs: [{}],
    extensions: { approval: { requestId: `req-${action}` } },
  };
}

/** The stream of `streamChatId`, opened while the session ran in `actionMode`. */
function streamOf(streamChatId: string, actionMode: string): StreamCtx {
  const state = {
    chatId: streamChatId,
    actionMode,
    messages: [],
    messageAppeared: false,
    loading: true,
    scheduler: {} as StreamHandlerState['scheduler'],
  } as unknown as StreamHandlerState;
  return {
    data: { type: 'tool_approval_request', messageId: 'msg-1', data: approvalPayload('alpha') } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state,
    actions: { setLoading: vi.fn(), setMessages: vi.fn(), setMessageAppeared: vi.fn() } as never,
    files: [],
  };
}

describe('toolsProgressEvents approval card ownership', () => {
  beforeEach(() => {
    useToolApprovalStore.getState().clearAll();
    // The chat the user has open now: a different chat, in a different mode.
    useChatStore.setState({ chatId: OPEN_CHAT, actionMode: 'fast' });
  });

  it('attributes the card to the streaming chat and its mode, not the open chat', async () => {
    await toolsProgressEvents(streamOf(BACKGROUND_CHAT, 'deep_research'));
    await vi.dynamicImportSettled();

    const [queued] = useToolApprovalStore.getState().queue;
    expect(queued?.chatId).toBe(BACKGROUND_CHAT);
    expect(queued?.actionMode).toBe('deep_research');
  });

  it('attributes the card to its own chat when that chat is the open one', async () => {
    await toolsProgressEvents(streamOf(OPEN_CHAT, 'agent'));
    await vi.dynamicImportSettled();

    const [queued] = useToolApprovalStore.getState().queue;
    expect(queued?.chatId).toBe(OPEN_CHAT);
    expect(queued?.actionMode).toBe('agent');
  });
});
