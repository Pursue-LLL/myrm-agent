import { describe, expect, it } from 'vitest';

import {
  batchUsesInlineVisualSurface,
  partitionApprovalQueue,
  usesInlineVisualApprovalSurface,
} from '@/lib/approval/visualApprovalSurface';
import type { ToolApprovalRequest } from '@/store/chat/types';

function makeRequest(overrides: Partial<ToolApprovalRequest>): ToolApprovalRequest {
  return {
    requestId: 'req-1',
    toolName: 'file_write_tool',
    toolInput: {},
    reason: 'test',
    timeoutSeconds: 60,
    expiresAt: Date.now() + 60_000,
    timeoutBehavior: 'deny',
    messageId: 'msg-1',
    displayMode: 'approval',
    chatId: 'chat-1',
    actionMode: 'agent',
    ...overrides,
  };
}

describe('visualApprovalSurface', () => {
  it('routes browser and desktop tools to inline surface', () => {
    const queue = [makeRequest({ requestId: 'browser', toolName: 'browser_click' })];

    expect(usesInlineVisualApprovalSurface(queue[0], queue)).toBe(true);
  });

  it('keeps non-visual tools on modal surface', () => {
    const queue = [makeRequest({ requestId: 'shell', toolName: 'shell_tool' })];

    expect(usesInlineVisualApprovalSurface(queue[0], queue)).toBe(false);
  });

  it('keeps entire batch on inline surface when any tool is visual', () => {
    const queue = [
      makeRequest({ requestId: 'b0', batchId: 'batch-a', batchIndex: 0, toolName: 'browser_click' }),
      makeRequest({ requestId: 'b1', batchId: 'batch-a', batchIndex: 1, toolName: 'shell_tool' }),
    ];

    expect(batchUsesInlineVisualSurface('batch-a', queue)).toBe(true);
    expect(usesInlineVisualApprovalSurface(queue[1], queue)).toBe(true);
  });

  it('partitions queue into inline and modal requests', () => {
    const queue = [
      makeRequest({ requestId: 'inline', toolName: 'desktop_vision_tool' }),
      makeRequest({ requestId: 'modal', toolName: 'shell_tool' }),
    ];

    const { inlineRequests, modalRequests } = partitionApprovalQueue(queue);

    expect(inlineRequests.map((request) => request.requestId)).toEqual(['inline']);
    expect(modalRequests.map((request) => request.requestId)).toEqual(['modal']);
  });
});
