import type { ToolApprovalRequest } from '@/store/chat/types';

/**
 * [INPUT] Pending approval requests selected for bulk action
 * [OUTPUT] Resume groups keyed by batchId or chat/message
 * [POS] Bulk approve/reject grouping before stream resume
 */

export function groupRequestsForBulkResume(requests: ToolApprovalRequest[]): ToolApprovalRequest[][] {
  const batchGroups = new Map<string, ToolApprovalRequest[]>();
  const singlesByMessage = new Map<string, ToolApprovalRequest[]>();

  for (const request of requests) {
    if (request.batchId) {
      const group = batchGroups.get(request.batchId) ?? [];
      group.push(request);
      batchGroups.set(request.batchId, group);
      continue;
    }

    const messageKey = `${request.chatId}:${request.messageId}`;
    const group = singlesByMessage.get(messageKey) ?? [];
    group.push(request);
    singlesByMessage.set(messageKey, group);
  }

  const groups: ToolApprovalRequest[][] = [];

  for (const group of batchGroups.values()) {
    groups.push(group.sort((a, b) => (a.batchIndex ?? 0) - (b.batchIndex ?? 0)));
  }

  for (const group of singlesByMessage.values()) {
    groups.push(group);
  }

  return groups;
}
