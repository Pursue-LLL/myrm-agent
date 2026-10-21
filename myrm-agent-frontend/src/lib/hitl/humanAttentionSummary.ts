/**
 * [INPUT]
 * - @/store/chat/clarificationState::findActivePendingClarification
 * - @/store/chat/types::Message
 * - @/lib/approval/visualApprovalSurface::partitionApprovalQueue
 * - @/store/useToolApprovalStore queue items
 * - @/store/useDesktopControlApprovalStore pending flag
 *
 * [OUTPUT]
 * - buildHumanAttentionSummary: ordered pending HITL items for the active chat
 *
 * [POS]
 * Pure aggregation for HumanAttentionBar (clarify, desktop gate, tool/visual approval).
 */

import { partitionApprovalQueue } from '@/lib/approval/visualApprovalSurface';
import { findActivePendingClarification } from '@/store/chat/clarificationState';
import type { Message, ToolApprovalRequest } from '@/store/chat/types';

export type HumanAttentionKind = 'clarify' | 'desktop_control' | 'tool_approval' | 'visual_approval';

export interface HumanAttentionItem {
  kind: HumanAttentionKind;
  messageId: string;
  summary: string;
  priority: number;
}

const KIND_PRIORITY: Record<HumanAttentionKind, number> = {
  clarify: 0,
  desktop_control: 1,
  visual_approval: 2,
  tool_approval: 3,
};

export interface HumanAttentionSummaryInput {
  chatId: string | undefined;
  messages: Message[];
  approvalQueue: ToolApprovalRequest[];
  desktopControlPending: boolean;
  desktopControlMessageId: string;
  desktopControlAppName: string;
  desktopControlReason: string;
}

export function buildHumanAttentionSummary(input: HumanAttentionSummaryInput): HumanAttentionItem[] {
  const items: HumanAttentionItem[] = [];
  if (!input.chatId) {
    return items;
  }

  const clarify = findActivePendingClarification(input.messages);
  if (clarify) {
    const formTitle = clarify.clarification.form?.title?.trim();
    const question = clarify.clarification.question?.trim();
    const title = clarify.clarification.title?.trim();
    const summary =
      (formTitle && formTitle.length > 0 ? formTitle : null) ??
      (title && title.length > 0 ? title : null) ??
      (question && question.length > 0 ? question : null) ??
      'clarify';
    items.push({
      kind: 'clarify',
      messageId: clarify.messageId,
      summary,
      priority: KIND_PRIORITY.clarify,
    });
  }

  if (input.desktopControlPending && input.desktopControlMessageId) {
    const app = input.desktopControlAppName.trim();
    const summary = app.length > 0 ? app : input.desktopControlReason.trim() || 'desktop_control';
    items.push({
      kind: 'desktop_control',
      messageId: input.desktopControlMessageId,
      summary,
      priority: KIND_PRIORITY.desktop_control,
    });
  }

  const chatQueue = input.approvalQueue.filter((request) => request.chatId === input.chatId);
  const { inlineRequests, modalRequests } = partitionApprovalQueue(chatQueue);

  for (const request of inlineRequests) {
    items.push({
      kind: 'visual_approval',
      messageId: String(request.messageId),
      summary: request.toolName,
      priority: KIND_PRIORITY.visual_approval,
    });
  }

  for (const request of modalRequests) {
    items.push({
      kind: 'tool_approval',
      messageId: String(request.messageId),
      summary: request.toolName,
      priority: KIND_PRIORITY.tool_approval,
    });
  }

  items.sort((a, b) => a.priority - b.priority || a.summary.localeCompare(b.summary));
  return items;
}
