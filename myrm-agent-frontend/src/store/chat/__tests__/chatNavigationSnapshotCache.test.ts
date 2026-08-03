import { describe, expect, it, beforeEach } from 'vitest';

import {
  extractNavigationSnapshot,
  getChatNavigationSnapshot,
  getChatNavigationSnapshotCountForTests,
  resetChatNavigationSnapshotsForTests,
  resolvePaneSnapshotBase,
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

  it('extractNavigationSnapshot preserves composer media state (files, cameraFrames, mentionReferences)', () => {
    const mockFiles = [
      { fileName: 'screenshot.png', fileExtension: 'png', fileType: 'uploaded' as const },
      { fileName: 'doc.pdf', fileExtension: 'pdf', fileType: 'uploaded' as const, id: 'f-1' },
    ];
    const mockCameraFrames = ['data:image/jpeg;base64,abc', 'data:image/jpeg;base64,def'];
    const mockMentionReferences = [
      { type: 'file' as const, path: '/src/index.ts', display: 'index.ts' },
    ];

    const snapshot = extractNavigationSnapshot({
      messages: [],
      isMessagesLoaded: true,
      files: mockFiles,
      cameraFrames: mockCameraFrames,
      mentionReferences: mockMentionReferences,
    } as Parameters<typeof extractNavigationSnapshot>[0]);

    expect(snapshot.files).toEqual(mockFiles);
    expect(snapshot.cameraFrames).toEqual(mockCameraFrames);
    expect(snapshot.mentionReferences).toEqual(mockMentionReferences);
  });

  it('round-trips composer media through save/get cycle', () => {
    const mockFiles = [{ fileName: 'photo.jpg', fileExtension: 'jpg', fileType: 'uploaded' as const }];
    const snapshot = extractNavigationSnapshot({
      messages: [],
      isMessagesLoaded: true,
      files: mockFiles,
      cameraFrames: ['frame-1'],
      mentionReferences: [{ type: 'file' as const, path: '/a.ts', display: 'a.ts' }],
    } as Parameters<typeof extractNavigationSnapshot>[0]);

    saveChatNavigationSnapshot('media-chat', snapshot);
    const restored = getChatNavigationSnapshot('media-chat');

    expect(restored!.files).toEqual(mockFiles);
    expect(restored!.cameraFrames).toEqual(['frame-1']);
    expect(restored!.mentionReferences).toEqual([{ type: 'file', path: '/a.ts', display: 'a.ts' }]);
  });

  it('extractNavigationSnapshot preserves session MoA preset per chat', () => {
    const snapshot = extractNavigationSnapshot({
      messages: [],
      activeMoaPresetId: 'default',
    } as Parameters<typeof extractNavigationSnapshot>[0]);

    expect(snapshot.activeMoaPresetId).toBe('default');
  });

  it('round-trips activeMoaPresetId through save/get cycle', () => {
    const snapshot = extractNavigationSnapshot({
      messages: [],
      isMessagesLoaded: true,
      activeMoaPresetId: 'default',
    } as Parameters<typeof extractNavigationSnapshot>[0]);

    saveChatNavigationSnapshot('moa-chat', snapshot);
    expect(getChatNavigationSnapshot('moa-chat')?.activeMoaPresetId).toBe('default');
  });

  it('resolvePaneSnapshotBase seeds session config from LRU when pane snapshot is empty', () => {
    saveChatNavigationSnapshot('pane-chat', {
      messages: [],
      activeMoaPresetId: 'fast',
      actionMode: 'agent',
    });

    const base = resolvePaneSnapshotBase('pane-chat', null);
    expect(base.activeMoaPresetId).toBe('fast');
    expect(base.actionMode).toBe('agent');
    expect(base.messages).toEqual([]);
  });

  it('resolvePaneSnapshotBase prefers pane session fields over LRU', () => {
    saveChatNavigationSnapshot('pane-chat', {
      messages: [],
      activeMoaPresetId: 'default',
    });

    const base = resolvePaneSnapshotBase('pane-chat', {
      messages: [{ id: 'm1' }],
      activeMoaPresetId: 'review',
    } as Parameters<typeof resolvePaneSnapshotBase>[1]);

    expect(base.activeMoaPresetId).toBe('review');
    expect(base.messages).toEqual([{ id: 'm1' }]);
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
