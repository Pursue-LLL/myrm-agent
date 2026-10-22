/**
 * The subagent store holds the tree of the chat the user has open, so only that chat's stream may write it.
 *
 * Real scenario: chat A is researching three competitors with subagents while the user opens chat B (or presses "new
 * chat"). A's stream keeps running in the background; its subagents must not show up in B's task tray, where "stop all"
 * would act on B and leave A's subagents running. A's own messages are routed per chat and are not affected.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import { useSubagentStore } from '@/store/chat/useSubagentStore';
import useChatStore from '@/store/useChatStore';
import type { StreamCtx } from '../../streamContext';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import { subagentEvents } from '../subagentEvents';

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
    data: { messageId: 'msg-1', ...(data as object) } as StreamCtx['data'],
    input: '',
    sources: undefined,
    added: false,
    state,
    actions,
    recievedMessage: '',
    files: [],
  };
}

/** Runs one stream event through the handler and lets its lazily loaded store write land. */
async function handle(data: unknown, streamChatId: string): Promise<StreamCtx> {
  const ctx = buildCtx(data, streamChatId);
  await subagentEvents(ctx);
  await vi.dynamicImportSettled();
  await new Promise((resolve) => setTimeout(resolve, 0));
  return ctx;
}

const nodeIds = () => Object.keys(useSubagentStore.getState().nodes);

const start = (taskId: string) => ({
  type: AgentEventType.SUBAGENT_START,
  data: { task_id: taskId, parent_task_id: '', agent_type: 'researcher', description: 'Compare vendors' },
});

describe('subagent stream events and the open chat', () => {
  beforeEach(() => {
    useSubagentStore.getState().clear();
    useChatStore.setState({ chatId: OPEN_CHAT });
  });

  describe('SUBAGENT_START', () => {
    it('adds the node when the stream belongs to the open chat', async () => {
      await handle(start('task-1'), OPEN_CHAT);

      expect(nodeIds()).toEqual(['task-1']);
    });

    it('keeps a background chat out of the tree but still records it in its own messages', async () => {
      const ctx = await handle(start('task-1'), BACKGROUND_CHAT);

      expect(nodeIds()).toEqual([]);
      expect(ctx.actions.setMessages).toHaveBeenCalledTimes(1);
    });

    it('keeps every stream out of the tree while the store holds no chat id yet', async () => {
      useChatStore.setState({ chatId: undefined });

      await handle(start('task-1'), BACKGROUND_CHAT);

      expect(nodeIds()).toEqual([]);
    });

    it('drops the write when the user switches chat while the store is still loading', async () => {
      const ctx = buildCtx(start('task-1'), OPEN_CHAT);

      await subagentEvents(ctx);
      useChatStore.setState({ chatId: BACKGROUND_CHAT });
      await vi.dynamicImportSettled();
      await new Promise((resolve) => setTimeout(resolve, 0));

      expect(nodeIds()).toEqual([]);
    });
  });

  describe('SUBAGENT_PROGRESS', () => {
    const progress = (taskId: string) => ({
      type: AgentEventType.SUBAGENT_PROGRESS,
      data: { task_id: taskId, progress: 0.5, current_step: 'Reading', token_usage: { total_tokens: 120 } },
    });

    it('updates the node of the open chat', async () => {
      await handle(start('task-1'), OPEN_CHAT);

      await handle(progress('task-1'), OPEN_CHAT);

      expect(useSubagentStore.getState().nodes['task-1']).toMatchObject({ progress: 50, last_tool: 'Reading' });
      expect(useSubagentStore.getState().nodes['task-1'].token_usage).toEqual({ total_tokens: 120 });
    });

    it('does not create a placeholder node from the token usage of a background chat', async () => {
      await handle(progress('task-9'), BACKGROUND_CHAT);

      expect(nodeIds()).toEqual([]);
    });
  });

  describe('events that change an existing node', () => {
    beforeEach(() => {
      useSubagentStore.getState().upsertNode({ task_id: 'task-1', status: 'running' });
    });

    it('SUBAGENT_LOG appends to the node only for the open chat', async () => {
      const log = { type: AgentEventType.SUBAGENT_LOG, data: { task_id: 'task-1', level: 'INFO', message: 'Reading' } };

      await handle(log, BACKGROUND_CHAT);
      expect(useSubagentStore.getState().nodes['task-1'].stream).toBeUndefined();

      await handle(log, OPEN_CHAT);
      expect(useSubagentStore.getState().nodes['task-1'].stream).toHaveLength(1);
    });

    it('SUBAGENT_STALE marks the node only for the open chat', async () => {
      const stale = {
        type: AgentEventType.SUBAGENT_STALE,
        data: { task_id: 'task-1', stale_duration_seconds: 120, wasted_tokens: 50, agent_type: 'researcher' },
      };

      await handle(stale, BACKGROUND_CHAT);
      expect(useSubagentStore.getState().nodes['task-1'].stale).toBeUndefined();

      await handle(stale, OPEN_CHAT);
      expect(useSubagentStore.getState().nodes['task-1'].stale).toBe(true);
    });
  });

  describe('FISSION_TOPOLOGY', () => {
    const topology = {
      type: AgentEventType.FISSION_TOPOLOGY,
      data: { fission_id: 'fission-1', nodes: [], total_cost_usd: 0 },
    };

    it('sets the topology for the open chat and ignores a background chat', async () => {
      await handle(topology, BACKGROUND_CHAT);
      expect(useSubagentStore.getState().fissionTopology).toBeNull();

      await handle(topology, OPEN_CHAT);
      expect(useSubagentStore.getState().fissionTopology?.fission_id).toBe('fission-1');
    });
  });

  describe('TEAMMATE_MESSAGE', () => {
    const message = {
      type: AgentEventType.TEAMMATE_MESSAGE,
      data: { message_id: 'm-1', from_task_id: 'task-from', to_task_id: 'task-to', body: 'Found it', created_at: 1 },
    };
    const onTeammateMessage = vi.fn();

    beforeEach(() => {
      onTeammateMessage.mockReset();
      window.addEventListener('teammate_message', onTeammateMessage);
      useSubagentStore.getState().upsertNode({ task_id: 'task-from', status: 'running' });
      useSubagentStore.getState().upsertNode({ task_id: 'task-to', status: 'running' });
    });

    afterEach(() => {
      window.removeEventListener('teammate_message', onTeammateMessage);
    });

    it('delivers the message and tells the dashboard which chat it belongs to', async () => {
      await handle(message, OPEN_CHAT);

      expect(useSubagentStore.getState().nodes['task-to'].teammateMessages).toHaveLength(1);
      expect(onTeammateMessage).toHaveBeenCalledTimes(1);
      expect((onTeammateMessage.mock.calls[0][0] as CustomEvent).detail.chat_id).toBe(OPEN_CHAT);
    });

    it('neither delivers the message of a background chat nor announces it for the open chat', async () => {
      await handle(message, BACKGROUND_CHAT);

      expect(useSubagentStore.getState().nodes['task-to'].teammateMessages).toBeUndefined();
      expect(onTeammateMessage).not.toHaveBeenCalled();
    });
  });
});
