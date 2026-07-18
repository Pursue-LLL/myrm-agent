import { describe, expect, it, vi } from 'vitest';

vi.mock('../handlerDeps', () => ({
  AgentEventType: {
    MEMORY_BRIEF: 'memory_brief',
  },
  findAssistantMessageIndex: vi.fn((messages: Array<{ messageId: string; role: string }>, messageId: string) =>
    messages.findIndex((msg) => msg.role === 'assistant' && msg.messageId === messageId),
  ),
}));

import { memoryBriefEvents } from '../memoryBriefEvents';
import type { StreamCtx } from '../../streamContext';

const briefPayload = {
  snapshot_id: 'snap-1',
  generated_at_ms: 1000,
  namespaces: ['global', 'agent:default'],
  is_cold_start: false,
  stable: {
    working_state: false,
    profile_keys: ['language'],
    instruction_count: 1,
    rule_count: 2,
  },
  learned: {
    preference_count: 2,
    rule_count: 1,
    correction_count: 0,
    preference_ids: ['mem-p1'],
    rule_ids: ['mem-r1'],
  },
};

function makeCtx(messages: Array<Record<string, unknown>>): StreamCtx {
  const state = {
    messages,
    messageAppeared: false,
    loading: true,
  };
  return {
    data: {
      type: 'memory_brief',
      messageId: 'msg-1',
      data: briefPayload,
    } as never,
    input: '',
    sources: undefined,
    added: false,
    recievedMessage: '',
    state: state as never,
    actions: {
      setMessages: (updater: (draft: typeof state) => void) => updater(state),
    } as never,
    files: [],
  };
}

describe('memoryBriefEvents', () => {
  it('creates assistant message when stream has no assistant yet', async () => {
    const ctx = makeCtx([
      {
        messageId: 'u-1',
        chatId: 'chat-1',
        role: 'user',
        content: 'hello',
        createdAt: new Date(),
      },
    ]);

    const result = await memoryBriefEvents(ctx);

    expect(result).not.toBeNull();
    expect(result?.added).toBe(true);
    expect(ctx.state.messages).toHaveLength(2);
    expect(ctx.state.messages[1]).toMatchObject({
      role: 'assistant',
      messageId: 'msg-1',
      memoryBriefSnapshotId: 'snap-1',
      memoryBrief: expect.objectContaining({ snapshot_id: 'snap-1' }),
    });
    expect((ctx.state as unknown as { messageAppeared: boolean }).messageAppeared).toBe(true);
  });

  it('updates existing assistant message instead of pushing duplicate', async () => {
    const ctx = makeCtx([
      {
        messageId: 'msg-1',
        chatId: 'chat-1',
        role: 'assistant',
        content: '',
        createdAt: new Date(),
      },
    ]);
    ctx.added = true;

    const result = await memoryBriefEvents(ctx);

    expect(result).not.toBeNull();
    expect(result?.added).toBe(true);
    expect(ctx.state.messages).toHaveLength(1);
    expect(ctx.state.messages[0]).toMatchObject({
      memoryBriefSnapshotId: 'snap-1',
      memoryBrief: expect.objectContaining({ snapshot_id: 'snap-1' }),
    });
  });
});

