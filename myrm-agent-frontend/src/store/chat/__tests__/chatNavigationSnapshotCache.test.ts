import { describe, expect, it, beforeEach } from 'vitest';

import {
  extractNavigationSnapshot,
  getChatNavigationSnapshot,
  getChatNavigationSnapshotCountForTests,
  resetChatNavigationSnapshotsForTests,
  saveChatNavigationSnapshot,
} from '@/store/chat/chatNavigationSnapshotCache';

describe('chatNavigationSnapshotCache', () => {
  beforeEach(() => {
    resetChatNavigationSnapshotsForTests();
  });

  it('stores and retrieves snapshots by chat id', () => {
    saveChatNavigationSnapshot('chat-a', { messages: [], isMessagesLoaded: true });
    expect(getChatNavigationSnapshot('chat-a')).toEqual({ messages: [], isMessagesLoaded: true });
  });

  it('extractNavigationSnapshot clones agent and model fields', () => {
    const snapshot = extractNavigationSnapshot({
      messages: [],
      agentConfig: { agentId: 'a1', name: 'Agent' },
      actionMode: 'agent',
      selectedModels: { base: 'gpt-4', vision: null, reasoning: null },
      hasUserSelectedModel: true,
    } as Parameters<typeof extractNavigationSnapshot>[0]);

    expect(snapshot.agentConfig).toEqual({ agentId: 'a1', name: 'Agent' });
    expect(snapshot.hasUserSelectedModel).toBe(true);
  });

  it('evicts the oldest snapshot when capacity is exceeded', () => {
    for (let index = 0; index < 21; index += 1) {
      saveChatNavigationSnapshot(`chat-${index}`, { messages: [], isMessagesLoaded: true });
    }

    expect(getChatNavigationSnapshotCountForTests()).toBe(20);
    expect(getChatNavigationSnapshot('chat-0')).toBeNull();
    expect(getChatNavigationSnapshot('chat-20')).toEqual({ messages: [], isMessagesLoaded: true });
  });
});
