/**
 * [INPUT]
 * - store/chat/messageStream/handlers/ttsrEvents::ttsrEvents (POS: 捕获 ttsr_triggered 流式事件切片)
 *
 * [OUTPUT]
 * - ttsrEvents.test.ts: 单元测试套件，验证流式事件拦截追加、多轮重试累积与非目标事件忽略
 *
 * [POS]
 * 单元测试层。验证消息流切片中 TTSR 安全事件对聊天消息实体的原子状态变更。
 */

import { describe, expect, it, vi } from 'vitest';

vi.mock('../../types/agentStream/part1', () => ({
  AgentEventType: {
    TTSR_TRIGGERED: 'ttsr_triggered',
  },
}));

vi.mock('../../messageUtils', () => ({
  findAssistantMessageIndex: vi.fn((messages: Array<{ messageId: string; role: string }>, messageId: string) =>
    messages.findIndex((msg) => msg.role === 'assistant' && msg.messageId === messageId),
  ),
}));

import { ttsrEvents } from '../ttsrEvents';
import type { StreamCtx } from '../../streamContext';

function makeCtx(
  type: string,
  payload: Record<string, unknown> | undefined,
  messages: Array<Record<string, unknown>>,
): StreamCtx {
  const state = {
    messages,
    messageAppeared: false,
    loading: true,
  };
  return {
    data: {
      type,
      messageId: 'msg-assistant-1',
      data: payload,
    } as never,
    input: '',
    sources: undefined,
    added: true,
    recievedMessage: '',
    state: state as never,
    actions: {
      setMessages: (updater: (draft: typeof state) => void) => updater(state),
    } as never,
    files: [],
  };
}

describe('ttsrEvents', () => {
  it('appends ttsrInterventions to target assistant message on ttsr_triggered event', async () => {
    const messages = [
      { messageId: 'msg-user-1', role: 'user', content: 'run command' },
      { messageId: 'msg-assistant-1', role: 'assistant', content: '' },
    ];

    const ctx = makeCtx(
      'ttsr_triggered',
      {
        rule_id: 'rule_block_rm_rf',
        rule_name: 'Block Destructive Command',
        reminder: 'Root recursive delete is forbidden.',
        target: 'tool_args',
        retry_count: 1,
        max_retries: 2,
      },
      messages,
    );

    const result = await ttsrEvents(ctx);
    expect(result).not.toBeNull();

    const assistantMsg = messages[1] as {
      ttsrInterventions?: Array<{
        ruleId: string;
        ruleName: string;
        reminder: string;
        retryCount: number;
        maxRetries: number;
      }>;
    };

    expect(assistantMsg.ttsrInterventions).toBeDefined();
    expect(assistantMsg.ttsrInterventions).toHaveLength(1);
    expect(assistantMsg.ttsrInterventions?.[0].ruleId).toBe('rule_block_rm_rf');
    expect(assistantMsg.ttsrInterventions?.[0].ruleName).toBe('Block Destructive Command');
    expect(assistantMsg.ttsrInterventions?.[0].retryCount).toBe(1);
    expect(assistantMsg.ttsrInterventions?.[0].maxRetries).toBe(2);
  });

  it('ignores other event types and returns null', async () => {
    const messages = [{ messageId: 'msg-assistant-1', role: 'assistant', content: '' }];
    const ctx = makeCtx('other_event', {}, messages);

    const result = await ttsrEvents(ctx);
    expect(result).toBeNull();
    expect((messages[0] as Record<string, unknown>).ttsrInterventions).toBeUndefined();
  });

  it('accumulates multiple interventions across retries', async () => {
    const messages = [
      {
        messageId: 'msg-assistant-1',
        role: 'assistant',
        content: '',
        ttsrInterventions: [
          {
            ruleId: 'rule-1',
            ruleName: 'Rule 1',
            reminder: 'First attempt',
            retryCount: 1,
            maxRetries: 2,
          },
        ],
      },
    ];

    const ctx = makeCtx(
      'ttsr_triggered',
      {
        rule_id: 'rule-2',
        rule_name: 'Rule 2',
        reminder: 'Second attempt',
        retry_count: 2,
        max_retries: 2,
      },
      messages,
    );

    await ttsrEvents(ctx);

    const assistantMsg = messages[0] as {
      ttsrInterventions?: Array<{ ruleId: string; retryCount: number }>;
    };
    expect(assistantMsg.ttsrInterventions).toHaveLength(2);
    expect(assistantMsg.ttsrInterventions?.[1].ruleId).toBe('rule-2');
    expect(assistantMsg.ttsrInterventions?.[1].retryCount).toBe(2);
  });
});
