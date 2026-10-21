import type { ToolApprovalRequest } from '@/store/chat/types';

import { isVisualApprovalToolName } from './visualApprovalContext';

/**
 * [INPUT] Tool approval queue entries
 * [OUTPUT] inline vs modal surface classification helpers
 * [POS] Shared surface routing for ToolApprovalDialog, inline artifacts, and mobile board
 */

export function batchUsesInlineVisualSurface(batchId: string, queue: ToolApprovalRequest[]): boolean {
  return queue.some((request) => request.batchId === batchId && isVisualApprovalToolName(request.toolName));
}

export function usesInlineVisualApprovalSurface(request: ToolApprovalRequest, queue: ToolApprovalRequest[]): boolean {
  if (request.batchId) {
    return batchUsesInlineVisualSurface(request.batchId, queue);
  }
  return isVisualApprovalToolName(request.toolName);
}

export function usesModalApprovalSurface(request: ToolApprovalRequest, queue: ToolApprovalRequest[]): boolean {
  return !usesInlineVisualApprovalSurface(request, queue);
}

export function partitionApprovalQueue(queue: ToolApprovalRequest[]): {
  inlineRequests: ToolApprovalRequest[];
  modalRequests: ToolApprovalRequest[];
} {
  const inlineRequests: ToolApprovalRequest[] = [];
  const modalRequests: ToolApprovalRequest[] = [];

  for (const request of queue) {
    if (usesInlineVisualApprovalSurface(request, queue)) {
      inlineRequests.push(request);
    } else {
      modalRequests.push(request);
    }
  }

  return { inlineRequests, modalRequests };
}
