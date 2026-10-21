/**
 * 董事长把关审批卡片与可视化授权中枢类型定义
 * 严禁 any 类型，确保严格 Type Hints 与只读保障
 */

export type ApprovalRiskLevel = 'low' | 'medium' | 'high' | 'critical';

export type ApprovalActionType = 'publish' | 'delete' | 'payment' | 'deploy' | 'custom';

export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'modified_approved';

export interface ApprovalRequest {
  readonly id: string;
  readonly taskId: string;
  readonly agentId: string;
  readonly agentName: string;
  readonly actionType: ApprovalActionType;
  readonly actionTitle: string;
  readonly targetChannel: string;
  readonly summary: string;
  readonly proposedContent: string;
  readonly modifiedContent?: string;
  readonly riskLevel: ApprovalRiskLevel;
  readonly riskReason: string;
  readonly createdAt: string;
  readonly status: ApprovalStatus;
  readonly feedbackComment?: string;
  readonly metadata?: Record<string, string>;
}

export interface ApprovalDecision {
  readonly decision: 'approve' | 'reject' | 'modify_and_approve';
  readonly modifiedContent?: string;
  readonly feedbackComment?: string;
}

export interface ApprovalStats {
  readonly pendingCount: number;
  readonly approvedCount: number;
  readonly rejectedCount: number;
  readonly highRiskCount: number;
  readonly totalCount: number;
}
