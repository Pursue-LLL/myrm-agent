import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { ChatState, Message } from '@/store/chat/types';
import {
  resetChatNavigationSnapshotsForTests,
  saveChatNavigationSnapshot,
} from '@/store/chat/chatNavigationSnapshotCache';
import { resolveInstantChatSnapshot } from '@/store/chat/messageManagement';

const workspacePanes: Array<{ chatId: string | null; snapshot: Partial<ChatState> | null }> = [];

vi.mock('@/store/useWorkspaceStore', () => ({
  default: {
    getState: () => ({ panes: workspacePanes }),
  },
}));

describe('resolveInstantChatSnapshot', () => {
  beforeEach(() => {
    resetChatNavigationSnapshotsForTests();
    workspacePanes.length = 0;
  });

  it('prefers LRU session config when pane snapshot is partial', () => {
    const agentConfig = { agentId: 'agent-1', name: 'Research Agent' } as ChatState['agentConfig'];

    saveChatNavigationSnapshot('chat-a', {
      messages: [{ id: 'm1', role: 'user', content: 'cached' } as Message],
      agentConfig,
      actionMode: 'deep_research',
      selectedModels: { base: 'gpt-4', vision: null, reasoning: null },
      hasUserSelectedModel: true,
      isMessagesLoaded: true,
      loading: false,
    });

    workspacePanes.push({
      chatId: 'chat-a',
      snapshot: {
        messages: [{ id: 'm2', role: 'assistant', content: 'streaming' } as Message],
        loading: true,
        messageAppeared: true,
      },
    });

    const resolved = resolveInstantChatSnapshot('chat-a');

    expect(resolved?.agentConfig).toEqual(agentConfig);
    expect(resolved?.actionMode).toBe('deep_research');
    expect(resolved?.selectedModels).toEqual({ base: 'gpt-4', vision: null, reasoning: null });
    expect(resolved?.messages).toEqual([{ id: 'm2', role: 'assistant', content: 'streaming' }]);
    expect(resolved?.loading).toBe(true);
    expect(resolved?.messageAppeared).toBe(true);
  });

  it('keeps LRU messages when pane snapshot is stale and not loading', () => {
    saveChatNavigationSnapshot('chat-a', {
      messages: [
        { id: 'm1', role: 'user', content: 'latest' } as Message,
        { id: 'm2', role: 'assistant', content: 'reply' } as Message,
      ],
      isMessagesLoaded: true,
      loading: false,
    });

    workspacePanes.push({
      chatId: 'chat-a',
      snapshot: {
        messages: [{ id: 'm0', role: 'user', content: 'stale' } as Message],
        loading: false,
        messageAppeared: false,
      },
    });

    const resolved = resolveInstantChatSnapshot('chat-a');

    expect(resolved?.messages).toHaveLength(2);
    expect(resolved?.messages?.[0]?.content).toBe('latest');
    expect(resolved?.loading).toBe(false);
  });

  it('falls back to pane snapshot when LRU is missing', () => {
    workspacePanes.push({
      chatId: 'chat-b',
      snapshot: {
        messages: [{ id: 'm1', role: 'user', content: 'pane only' } as Message],
        isMessagesLoaded: true,
        loading: false,
      },
    });

    expect(resolveInstantChatSnapshot('chat-b')).toEqual({
      messages: [{ id: 'm1', role: 'user', content: 'pane only' }],
      isMessagesLoaded: true,
      loading: false,
    });
  });
});
