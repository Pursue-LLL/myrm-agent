import { describe, expect, it } from 'vitest';
import {
  isMemoryRecallToolName,
  mergeCitedMemoryReferences,
  normalizeCitedMemoryReferences,
} from '../memoryCitationUtils';
import type { CitedMemoryReference } from '../types';

describe('memoryCitationUtils', () => {
  it('recognizes canonical and runtime memory recall tool names', () => {
    expect(isMemoryRecallToolName('memory_recall')).toBe(true);
    expect(isMemoryRecallToolName('memory_recall_tool')).toBe(true);
    expect(isMemoryRecallToolName('conversation_search')).toBe(false);
    expect(isMemoryRecallToolName('web_search')).toBe(false);
    expect(isMemoryRecallToolName(undefined)).toBe(false);
  });

  it('normalizes snake_case and camelCase citation payloads', () => {
    const refs = normalizeCitedMemoryReferences([
      {
        id: 'mem-1',
        memory_type: 'semantic',
        content: 'Customer A prefers concise weekly reports.',
        score: 0.91,
        created_at: '2026-04-29T01:00:00Z',
        primary_namespace: 'shared:customer-a',
        namespaces: ['global', 'shared:customer-a'],
        source_chat_id: 'chat-1',
        source_message_id: 'msg-1',
      },
      {
        id: 'mem-2',
        memoryType: 'episodic',
        primaryNamespace: 'agent:writer',
        sourceChatId: 'chat-2',
        sourceMessageId: 'msg-2',
      },
    ]);

    expect(refs).toEqual<CitedMemoryReference[]>([
      {
        id: 'mem-1',
        memoryType: 'semantic',
        content: 'Customer A prefers concise weekly reports.',
        score: 0.91,
        createdAt: '2026-04-29T01:00:00Z',
        primaryNamespace: 'shared:customer-a',
        namespaces: ['global', 'shared:customer-a'],
        sourceChatId: 'chat-1',
        sourceMessageId: 'msg-1',
      },
      {
        id: 'mem-2',
        memoryType: 'episodic',
        primaryNamespace: 'agent:writer',
        sourceChatId: 'chat-2',
        sourceMessageId: 'msg-2',
      },
    ]);
  });

  it('drops malformed and duplicate citation refs', () => {
    const refs = normalizeCitedMemoryReferences([
      { id: 'mem-1', content: 'first' },
      { id: 'mem-1', content: 'duplicate' },
      { id: '' },
      null,
      'mem-2',
    ]);

    expect(refs).toEqual([{ id: 'mem-1', content: 'first' }]);
  });

  it('merges incoming refs over existing refs by memory id', () => {
    const merged = mergeCitedMemoryReferences(
      [{ id: 'mem-1', content: 'old', score: 0.5 }],
      [
        { id: 'mem-1', content: 'new' },
        { id: 'mem-2', memoryType: 'semantic' },
      ],
    );

    expect(merged).toEqual([
      { id: 'mem-1', content: 'new', score: 0.5 },
      { id: 'mem-2', memoryType: 'semantic' },
    ]);
  });
});
