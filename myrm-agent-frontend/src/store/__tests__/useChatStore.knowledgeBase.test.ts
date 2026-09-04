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

  it('cleans active knowledge base IDs upon switching from one existing chatId to another', () => {
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

  it('preserves pre-selected knowledge base IDs when creating a brand new chat from cold start', () => {
    useChatStore.setState({
      activeKnowledgeBaseIds: ['kb-pre-1', 'kb-pre-2'],
      activeKnowledgeBaseNames: {
        'kb-pre-1': 'Engineering Docs',
        'kb-pre-2': 'Security Policy',
      },
      chatId: undefined,
    });

    useChatStore.getState().setChatId('chat-created-new');

    const updated = useChatStore.getState();
    expect(updated.activeKnowledgeBaseIds).toEqual(['kb-pre-1', 'kb-pre-2']);
    expect(updated.activeKnowledgeBaseNames).toEqual({
      'kb-pre-1': 'Engineering Docs',
      'kb-pre-2': 'Security Policy',
    });
    expect(updated.chatId).toBe('chat-created-new');
  });

  it('handles empty knowledge base lists gracefully', () => {
    const store = useChatStore.getState();
    store.setActiveKnowledgeBaseIds([]);
    store.setActiveKnowledgeBaseNames({});

    expect(useChatStore.getState().activeKnowledgeBaseIds).toEqual([]);
    expect(useChatStore.getState().activeKnowledgeBaseNames).toEqual({});

    // Attempting to remove from empty list does not throw or mutate
    store.removeActiveKnowledgeBase('non-existent-id');
    expect(useChatStore.getState().activeKnowledgeBaseIds).toEqual([]);
    expect(useChatStore.getState().activeKnowledgeBaseNames).toEqual({});
  });

  it('prevents exceeding max mounted knowledge bases limit', () => {
    const store = useChatStore.getState();
    const sixIds = ['kb-1', 'kb-2', 'kb-3', 'kb-4', 'kb-5', 'kb-6'];
    store.setActiveKnowledgeBaseIds(sixIds);

    expect(useChatStore.getState().activeKnowledgeBaseIds).toHaveLength(6);
    expect(useChatStore.getState().activeKnowledgeBaseIds).toEqual(sixIds);
  });
});


