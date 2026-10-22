/**
 * A background chat's compaction milestone belongs to that chat, not to the chat on screen.
 *
 * Real scenario: the user reads chat B while chat A compacts its context. A's "tokens saved" must not be
 * stamped onto B's milestone chip, and the refresh's API calls must not run against B either.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/utils/toast', () => ({ toast: { warning: vi.fn(), error: vi.fn(), success: vi.fn() } }));

import useChatStore from '@/store/useChatStore';
import { applyStatusProgressStep } from '../statusStreamProgressSteps';
import type { StreamCtx } from '../../streamContext';
import type { StreamHandlerState } from '../../types';

const OPEN_CHAT = 'chat-open';
const BACKGROUND_CHAT = 'chat-background';

function compactionCtx(streamChatId: string): StreamCtx {
  const state = {
    chatId: streamChatId,
    messages: [],
    messageAppeared: false,
    loading: true,
    scheduler: {} as StreamHandlerState['scheduler'],
  } as unknown as StreamHandlerState;
  return {
    data: {
      type: 'status',
      messageId: 'msg-1',
      step_key: 'context_compaction',
      tokens_saved: 4242,
      data: { phase: 'completed' },
    } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state,
    actions: { setMessages: vi.fn(), setLoading: vi.fn() } as never,
    files: [],
  };
}

describe('statusStreamProgressSteps compaction refresh scope', () => {
  const refreshCompactionState = vi.fn(async () => undefined);

  beforeEach(() => {
    refreshCompactionState.mockClear();
    useChatStore.setState({ chatId: OPEN_CHAT, lastCompactionMeta: null, refreshCompactionState });
  });

  it('refreshes the compaction state when the compacting chat is the open one', async () => {
    await applyStatusProgressStep(compactionCtx(OPEN_CHAT), 'context_compaction');

    expect(refreshCompactionState).toHaveBeenCalledTimes(1);
    expect(refreshCompactionState).toHaveBeenCalledWith(OPEN_CHAT, { tokensSaved: 4242, snapshotPath: undefined });
  });

  it("leaves the open chat's milestone alone when a background chat compacts", async () => {
    await applyStatusProgressStep(compactionCtx(BACKGROUND_CHAT), 'context_compaction');

    expect(refreshCompactionState).not.toHaveBeenCalled();
  });
});
