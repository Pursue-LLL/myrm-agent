import { describe, expect, it } from 'vitest';

import { buildHumanAttentionSummary } from '../humanAttentionSummary';
import type { Message, ToolApprovalRequest } from '@/store/chat/types';

const baseMessage = (overrides: Partial<Message>): Message =>
  ({
    messageId: 'msg-1',
    role: 'assistant',
    content: '',
    ...overrides,
  }) as Message;

describe('buildHumanAttentionSummary', () => {
  it('orders clarify before desktop control and approvals', () => {
    const messages: Message[] = [
      baseMessage({
        messageId: 'msg-clarify',
        clarification: { answered: false, question: 'Pick one' },
      }),
    ];
    const queue: ToolApprovalRequest[] = [
      {
        chatId: 'chat-1',
        messageId: 'msg-tool',
        toolName: 'bash_code_execute_tool',
        expiresAt: Date.now() / 1000 + 60,
        requestId: 'r1',
        toolInput: {},
        reason: 'needs approval',
        timeoutSeconds: 60,
        timeoutBehavior: 'deny',
        displayMode: 'approval',
        actionMode: 'agent',
      },
    ];

    const items = buildHumanAttentionSummary({
      chatId: 'chat-1',
      messages,
      approvalQueue: queue,
      desktopControlPending: true,
      desktopControlMessageId: 'msg-desktop',
      desktopControlAppName: 'Mail',
      desktopControlReason: 'send',
    });

    expect(items.map((item) => item.kind)).toEqual([
      'clarify',
      'desktop_control',
      'tool_approval',
    ]);
  });

  it('returns empty when chat id is missing', () => {
    expect(
      buildHumanAttentionSummary({
        chatId: undefined,
        messages: [],
        approvalQueue: [],
        desktopControlPending: false,
        desktopControlMessageId: '',
        desktopControlAppName: '',
        desktopControlReason: '',
      }),
    ).toEqual([]);
  });
});
