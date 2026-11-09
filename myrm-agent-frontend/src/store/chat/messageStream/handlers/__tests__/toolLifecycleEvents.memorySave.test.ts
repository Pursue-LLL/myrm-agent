import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AgentEventType } from '@/store/chat/types';
import { useMemoryStore } from '@/store/memory';
import type { StreamHandlerActions, StreamHandlerState } from '../../types';
import type { StreamCtx } from '../../streamContext';
import { toolLifecycleEvents } from '../toolLifecycleEvents';

function buildToolEndCtx(toolName: string): StreamCtx {
  const state: StreamHandlerState = {
    messages: [
      {
        messageId: 'msg-1',
        chatId: 'chat-1',
        createdAt: new Date(),
        role: 'assistant',
        content: '',
        progressSteps: [{ step_key: 'memory_step', tool_name: toolName }],
      },
    ],
    messageAppeared: false,
    loading: false,
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
    data: { type: AgentEventType.TOOL_END, messageId: 'msg-1', tool_name: toolName },
    input: '',
    sources: undefined,
    added: false,
    state,
    actions,
    recievedMessage: '',
    files: [],
  };
}

describe('toolLifecycleEvents memory save TOOL_END', () => {
  const fetchPendingMemories = vi.fn(async () => undefined);

  beforeEach(() => {
    fetchPendingMemories.mockClear();
    useMemoryStore.setState({ fetchPendingMemories });
  });

  it('refreshes the pending queue once the agent has saved a memory', async () => {
    await toolLifecycleEvents(buildToolEndCtx('memory_save_tool'));

    await vi.waitFor(() => {
      expect(fetchPendingMemories).toHaveBeenCalledExactlyOnceWith(true);
    });
  });

  it.each(['memory_search_tool', 'memory_manage_tool', 'web_search_tool'])(
    'leaves the pending queue alone after %s',
    async (toolName) => {
      await toolLifecycleEvents(buildToolEndCtx(toolName));
      await vi.dynamicImportSettled();

      expect(fetchPendingMemories).not.toHaveBeenCalled();
    },
  );
});
