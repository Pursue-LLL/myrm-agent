type DecisionType = 'approve' | 'edit' | 'reject';

export interface ApprovalDecision {
  type: DecisionType;
  args?: Record<string, unknown>;
  feedback?: string;
  guidance?: string;
  extensions: {
    allowAlways: boolean | { tool?: boolean; args?: boolean };
    allowDomain?: boolean;
  };
}

export interface ResumeDecisionsPayload {
  decisions: ApprovalDecision[];
}

/** LangGraph interrupt resume for semantic DOM HITL (matches harness _parse_interrupt_decision). */
export interface SemanticDomResumePayload {
  decision: 'approve' | 'reject';
  feedback?: string;
}

export type DrawerResumeValue = ResumeDecisionsPayload | SemanticDomResumePayload;

export interface ToolApprovalResolveExtra {
  edited_args?: Record<string, unknown>;
  feedback?: string;
  guidance?: string;
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
    ...(extra?.guidance && { guidance: extra.guidance }),
    extensions: {
      allowAlways: extra?.allow_always ?? false,
      ...(extra?.allow_domain && { allowDomain: true }),
    },
  };
}
