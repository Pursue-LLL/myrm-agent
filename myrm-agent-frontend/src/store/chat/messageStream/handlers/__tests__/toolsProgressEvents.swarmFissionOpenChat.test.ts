/**
 * The fission summary strip describes the swarm of the chat the user has open.
 *
 * Real scenario: chat A fans a task out to eight parallel workers while the user reads chat B. A's progress must not
 * paint "8 running" onto B's strip, yet a failure in A is still worth a toast because the user is not looking at A.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { warningToast } = vi.hoisted(() => ({ warningToast: vi.fn() }));
vi.mock('@/lib/utils/toast', () => ({ toast: { warning: warningToast } }));

import { AgentEventType } from '@/store/chat/types';
import { useSubagentStore } from '@/store/chat/useSubagentStore';
import useChatStore from '@/store/useChatStore';
import type { StreamCtx } from '../../streamContext';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import { toolsProgressEvents } from '../toolsProgressEvents';

const OPEN_CHAT = 'chat-open';
const BACKGROUND_CHAT = 'chat-background';

function buildCtx(data: unknown, streamChatId: string): StreamCtx {
  const state: StreamHandlerState = {
    chatId: streamChatId,
    messages: [],
    messageAppeared: false,
    loading: true,
    scheduler: {} as StreamHandlerState['scheduler'],
  };
  const actions: StreamHandlerActions = {
    setMessages: vi.fn(),
    setMessageAppeared: vi.fn(),
    setLoading: vi.fn(),
    _processSuggestions: vi.fn(async () => undefined),
    scheduleAutoSave: vi.fn(),
  };
  return {
    data: { messageId: 'msg-1', step_key: 'swarm_fission', count: 8, ...(data as object) } as StreamCtx['data'],
    input: '',
    sources: undefined,
    added: true,
    state,
    actions,
    recievedMessage: '',
    files: [],
  };
}

async function handle(data: unknown, streamChatId: string): Promise<void> {
  await toolsProgressEvents(buildCtx({ type: AgentEventType.TASKS_STEPS, ...(data as object) }, streamChatId));
  await vi.dynamicImportSettled();
  await new Promise((resolve) => setTimeout(resolve, 0));
}

describe('swarm fission progress and the open chat', () => {
  beforeEach(() => {
    useSubagentStore.getState().clear();
    useChatStore.setState({ chatId: OPEN_CHAT });
    warningToast.mockReset();
  });

  it('shows the running swarm of the open chat', async () => {
    await handle({ status: 'running' }, OPEN_CHAT);

    expect(useSubagentStore.getState().fissionBatch).toEqual({
      active: true,
      total: 8,
      completed: 0,
      failed: 0,
      partial: false,
    });
  });

  it('keeps the swarm of a background chat off the strip of the open chat', async () => {
    await handle({ status: 'running' }, BACKGROUND_CHAT);

    expect(useSubagentStore.getState().fissionBatch).toBeNull();
  });

  it('records the outcome of the open chat and warns about its failed workers', async () => {
    await handle({ status: 'partial_success', failed_count: 2, completed_count: 6 }, OPEN_CHAT);

    expect(useSubagentStore.getState().fissionBatch).toMatchObject({ active: false, completed: 6, failed: 2 });
    expect(warningToast).toHaveBeenCalledTimes(1);
  });

  it('still warns about failed workers of a background chat, without touching the strip', async () => {
    await handle({ status: 'partial_success', failed_count: 2, completed_count: 6 }, BACKGROUND_CHAT);

    expect(useSubagentStore.getState().fissionBatch).toBeNull();
    expect(warningToast).toHaveBeenCalledTimes(1);
  });
});
