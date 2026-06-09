/**
 * [INPUT]
 * - store/useApprovalStore::ApprovalPayload (POS: 全局 Drawer 审批队列契约)
 * - buildDrawerResumeValue::buildDrawerResumeValue (POS: Drawer resume decisions 构建)
 * - resumeApprovalStream::resumeApprovalStream (POS: SSE resume 执行)
 *
 * [OUTPUT]
 * - resumeDrawerApprovalStream()
 *
 * [POS]
 * Bridges ApprovalDrawer HTTP resolve to agent-stream Command(resume=...).
 */

import type { ApprovalPayload } from '@/store/useApprovalStore';
import type { ToolApprovalResolveExtra } from '@/lib/approval/approvalDecision';
import { buildDrawerResumeValue } from '@/lib/approval/buildDrawerResumeValue';
import { resumeApprovalStream } from '@/lib/approval/resumeApprovalStream';
import type { ToolApprovalRequest } from '@/store/chat/types/toolApproval';

async function createDrawerResumeAnchor(approval: ApprovalPayload): Promise<ToolApprovalRequest | null> {
  if (!approval.chat_id) {
    return null;
  }

  const { default: useChatStore } = await import('@/store/useChatStore');
  const chatState = useChatStore.getState();
  const actionMode =
    chatState.chatId === approval.chat_id ? chatState.actionMode : 'general';

  return {
    requestId: approval.approval_id,
    toolName: approval.payload?.tool_calls?.[0]?.name ?? approval.action_type,
    toolInput: approval.payload?.tool_calls?.[0]?.args ?? {},
    reason: approval.reason ?? '',
    timeoutSeconds: 300,
    expiresAt: Math.floor(Date.now() / 1000) + 300,
    timeoutBehavior: 'deny',
    messageId: crypto.randomUUID(),
    displayMode: 'approval',
    chatId: approval.chat_id,
    actionMode,
  };
}

/**
 * [INPUT] Resolved drawer approval + decision extras (allow_always, edited_args for edit)
 * [OUTPUT] Agent stream resumed via shared resumeApprovalStream
 * [POS] Bridges ApprovalDrawer HTTP resolve to LangGraph Command(resume=...) before DB resolve
 */
export async function resumeDrawerApprovalStream(
  approval: ApprovalPayload,
  action: 'approve' | 'reject' | 'edit',
  extra: ToolApprovalResolveExtra | undefined,
  resumeErrorMessage: string,
): Promise<void> {
  const anchor = await createDrawerResumeAnchor(approval);
  if (!anchor) {
    return;
  }

  const resumeValue = buildDrawerResumeValue(approval, action, extra);
  await resumeApprovalStream(anchor, resumeValue, resumeErrorMessage);
}
