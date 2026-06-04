import { describe, expect, it } from 'vitest';

import { groupRequestsForBulkResume } from '@/lib/approval/approvalBulkGroups';
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

describe('groupRequestsForBulkResume', () => {
  it('groups batch requests by batchId and preserves batch order', () => {
    const requests = [
      makeRequest({ requestId: 'b0', batchId: 'batch-a', batchIndex: 0 }),
      makeRequest({ requestId: 'b1', batchId: 'batch-a', batchIndex: 1 }),
      makeRequest({ requestId: 's1', toolName: 'shell_tool' }),
    ];

    const groups = groupRequestsForBulkResume(requests);

    expect(groups).toHaveLength(2);
    expect(groups[0].map((request) => request.requestId)).toEqual(['b0', 'b1']);
    expect(groups[1].map((request) => request.requestId)).toEqual(['s1']);
  });

  it('groups non-batch singles by chat and message', () => {
    const requests = [
      makeRequest({ requestId: 's1', messageId: 'msg-1' }),
      makeRequest({ requestId: 's2', messageId: 'msg-1' }),
      makeRequest({ requestId: 's3', messageId: 'msg-2' }),
    ];

    const groups = groupRequestsForBulkResume(requests);

    expect(groups).toHaveLength(2);
    expect(groups.find((group) => group.length === 2)?.map((request) => request.requestId)).toEqual(['s1', 's2']);
    expect(groups.find((group) => group.length === 1)?.[0].requestId).toBe('s3');
  });
});
