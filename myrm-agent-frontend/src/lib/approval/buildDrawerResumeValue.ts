/**
 * [INPUT]
 * - store/useApprovalStore::ApprovalPayload (POS: 全局 Drawer 审批队列契约)
 * - approvalDecision::buildApprovalDecision (POS: LangGraph decision 构建)
 *
 * [OUTPUT]
 * - shouldResumeDrawerApproval(), buildDrawerResumeValue(approve|reject|edit)
 *
 * [POS]
 * Resume payload builder for ApprovalDrawer subagent batch HITL (incl. shell edit).
 */

import type { ApprovalPayload } from '@/store/useApprovalStore';
import {
  buildApprovalDecision,
  type DrawerResumeValue,
  type ToolApprovalResolveExtra,
} from '@/lib/approval/approvalDecision';

const DRAWER_RESUME_ACTION_TYPES = new Set([
  'subagent_approval',
  'deploy_approval',
  'high_risk_dom_action',
]);

/**
 * [INPUT] Drawer approval record + user decision
 * [OUTPUT] LangGraph resume_value with per-tool decisions for batch subagent HITL
 * [POS] Resume payload builder for ApprovalDrawer resolve path
 */
export function shouldResumeDrawerApproval(actionType: string): boolean {
  return DRAWER_RESUME_ACTION_TYPES.has(actionType);
}

export function buildDrawerResumeValue(
  approval: ApprovalPayload,
  action: 'approve' | 'reject' | 'edit',
  extra?: ToolApprovalResolveExtra,
): DrawerResumeValue {
  const decisionType = action === 'reject' ? 'reject' : action === 'edit' ? 'edit' : 'approve';
  const resolveExtra: ToolApprovalResolveExtra = {
    ...extra,
    feedback: extra?.feedback ?? (action === 'reject' ? 'User rejected this action.' : undefined),
  };

  if (approval.action_type === 'high_risk_dom_action') {
    return {
      decision: action === 'reject' ? 'reject' : 'approve',
      ...(resolveExtra.feedback ? { feedback: resolveExtra.feedback } : {}),
    };
  }

  if (approval.action_type === 'subagent_approval') {
    const toolCount = approval.payload?.tool_calls?.length ?? 0;
    const decisionCount = Math.max(toolCount, 1);
    return {
      decisions: Array.from({ length: decisionCount }, () =>
        buildApprovalDecision(decisionType, resolveExtra),
      ),
    };
  }

  return {
    decisions: [buildApprovalDecision(decisionType, resolveExtra)],
  };
}
