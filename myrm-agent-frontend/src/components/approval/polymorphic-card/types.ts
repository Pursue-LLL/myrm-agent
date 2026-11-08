import type { ToolApprovalResolveExtra } from '@/lib/approval/approvalDecision';

export type DrawerDecisionAction = 'approve' | 'reject' | 'edit';

/** Resolves the approval; `extra` carries the grant, edit and guidance fields of the decision. */
export type ApprovalResolveHandler = (
  action: DrawerDecisionAction,
  comment?: string,
  edited_payload?: Record<string, unknown>,
  extra?: ToolApprovalResolveExtra,
) => Promise<void>;
