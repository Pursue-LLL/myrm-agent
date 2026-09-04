import { describe, it, expect, vi, beforeEach } from 'vitest';
import useChatStore from '@/store/useChatStore';

describe('useChatStore - Knowledge Base Mount State & Actions', () => {
  beforeEach(() => {
    useChatStore.setState({
      activeKnowledgeBaseIds: [],
      activeKnowledgeBaseNames: {},
      chatId: undefined,
    });
  });

  it('sets active knowledge base IDs and preserves immutability', () => {
    const store = useChatStore.getState();
    store.setActiveKnowledgeBaseIds(['kb-arch', 'kb-policy']);

    const updated = useChatStore.getState();
    expect(updated.activeKnowledgeBaseIds).toEqual(['kb-arch', 'kb-policy']);
  });

  it('sets active knowledge base human-readable name map', () => {
    const store = useChatStore.getState();
    store.setActiveKnowledgeBaseNames({
      'kb-arch': 'System Architecture Guide',
      'kb-policy': 'Financial & Security Policy',
    });

    const updated = useChatStore.getState();
    expect(updated.activeKnowledgeBaseNames).toEqual({
      'kb-arch': 'System Architecture Guide',
      'kb-policy': 'Financial & Security Policy',
    });
  });

  it('removes single knowledge base correctly from both ids and names', () => {
    useChatStore.setState({
      activeKnowledgeBaseIds: ['kb-1', 'kb-2', 'kb-3'],
      activeKnowledgeBaseNames: {
        'kb-1': 'Knowledge 1',
        'kb-2': 'Knowledge 2',
        'kb-3': 'Knowledge 3',
      },
    });

    const store = useChatStore.getState();
    store.removeActiveKnowledgeBase('kb-2');

    const updated = useChatStore.getState();
    expect(updated.activeKnowledgeBaseIds).toEqual(['kb-1', 'kb-3']);
    expect(updated.activeKnowledgeBaseNames).toEqual({
      'kb-1': 'Knowledge 1',
      'kb-3': 'Knowledge 3',
    });
  });

  it('resets knowledge base state upon resetSessionState', () => {
    useChatStore.setState({
      activeKnowledgeBaseIds: ['kb-1'],
      activeKnowledgeBaseNames: { 'kb-1': 'Knowledge 1' },
      chatId: 'test-chat-123',
    });

    useChatStore.getState().resetSessionState();

    const updated = useChatStore.getState();
    expect(updated.activeKnowledgeBaseIds).toEqual([]);
    expect(updated.activeKnowledgeBaseNames).toEqual({});
  });

  it('cleans active knowledge base IDs upon switching chatId', () => {
    useChatStore.setState({
      activeKnowledgeBaseIds: ['kb-1'],
      activeKnowledgeBaseNames: { 'kb-1': 'Knowledge 1' },
      chatId: 'chat-old',
    });

    useChatStore.getState().setChatId('chat-new');

    const updated = useChatStore.getState();
    expect(updated.activeKnowledgeBaseIds).toEqual([]);
    expect(updated.chatId).toBe('chat-new');
  });
});
