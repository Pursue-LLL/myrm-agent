type DecisionType = 'approve' | 'edit' | 'reject';

export interface ApprovalDecision {
  type: DecisionType;
  args?: Record<string, unknown>;
  feedback?: string;
  extensions: {
    allowAlways: boolean;
    allowDomain?: boolean;
  };
}

export interface ResumeDecisionsPayload {
  decisions: ApprovalDecision[];
}

export interface ToolApprovalResolveExtra {
  edited_args?: Record<string, unknown>;
  feedback?: string;
  allow_always?: boolean | { tool?: boolean; args?: boolean };
  allow_domain?: boolean;
}

/**
 * [INPUT] Decision type + optional edited args / feedback / allow flags
 * [OUTPUT] LangGraph-compatible approval decision object
 * [POS] Shared payload builder for single and bulk approval resume
 */
export function buildApprovalDecision(
  decision: DecisionType,
  extra?: ToolApprovalResolveExtra,
): ApprovalDecision {
  return {
    type: decision,
    args: extra?.edited_args,
    feedback: extra?.feedback,
    extensions: {
      allowAlways: extra?.allow_always ?? false,
      ...(extra?.allow_domain && { allowDomain: true }),
    },
  };
}
