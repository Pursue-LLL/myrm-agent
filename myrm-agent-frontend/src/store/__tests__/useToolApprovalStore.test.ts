import { beforeEach, describe, expect, it } from 'vitest';

import useToolApprovalStore from '@/store/useToolApprovalStore';
import type { ToolApprovalRequest } from '@/store/chat/types';

function makeRequest(overrides: Partial<ToolApprovalRequest>): ToolApprovalRequest {
  return {
    requestId: 'req-1',
    toolName: 'bash_code_execute_tool',
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

function queuedRequestIds(): string[] {
  return useToolApprovalStore.getState().queue.map((request) => request.requestId);
}

describe('useToolApprovalStore.addRequest', () => {
  beforeEach(() => {
    useToolApprovalStore.getState().clearAll();
  });

  it('queues the cards of different interrupts side by side', () => {
    const { addRequest } = useToolApprovalStore.getState();

    addRequest(makeRequest({ requestId: 'a', interruptId: 'int-a' }));
    addRequest(makeRequest({ requestId: 'b', interruptId: 'int-b' }));

    expect(queuedRequestIds()).toEqual(['a', 'b']);
  });

  it('keeps one card for an interrupt the run announces again after another card was answered', () => {
    const { addRequest } = useToolApprovalStore.getState();

    addRequest(makeRequest({ requestId: 'first', interruptId: 'int-a' }));
    addRequest(makeRequest({ requestId: 'announced-again', interruptId: 'int-a' }));

    expect(queuedRequestIds()).toEqual(['first']);
  });

  it('keeps the cards of one batched interrupt apart by their position in the batch', () => {
    const { addRequest } = useToolApprovalStore.getState();

    addRequest(makeRequest({ requestId: 'b_0', interruptId: 'int-a', batchId: 'b', batchIndex: 0 }));
    addRequest(makeRequest({ requestId: 'b_1', interruptId: 'int-a', batchId: 'b', batchIndex: 1 }));
    addRequest(makeRequest({ requestId: 'b_1-again', interruptId: 'int-a', batchId: 'b', batchIndex: 1 }));

    expect(queuedRequestIds()).toEqual(['b_0', 'b_1']);
  });

  it('queues a card without an interrupt id as before', () => {
    const { addRequest } = useToolApprovalStore.getState();

    addRequest(makeRequest({ requestId: 'x' }));
    addRequest(makeRequest({ requestId: 'y' }));

    expect(queuedRequestIds()).toEqual(['x', 'y']);
  });
});
