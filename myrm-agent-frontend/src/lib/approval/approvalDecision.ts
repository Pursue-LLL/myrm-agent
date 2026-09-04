import type { AllowAlwaysValue } from '@/lib/approval/allowAlwaysScope';

type DecisionType = 'approve' | 'edit' | 'reject';

export interface ApprovalDecision {
  type: DecisionType;
  args?: Record<string, unknown>;
  feedback?: string;
  guidance?: string;
  action_digest?: string;
  actionDigest?: string;
  extensions: {
    allowAlways: AllowAlwaysValue;
    ttlSeconds?: number;
    allowDomain?: boolean;
    grantDirectory?: boolean;
    grantDirectoryMeta?: { path: string; writable: boolean };
    actionDigest?: string;
    action_digest?: string;
  };
}

export interface DirectoryGrantOptimistic {
  path: string;
  writable: boolean;
  source: 'path_ask_grant';
}

export interface SpendReviewConfig {
  isSpend?: boolean;
  spendAmount?: number;
  spendCurrency?: string;
  actionDigest?: string;
}

export function extractSpendReviewConfig(
  reviewConfigs?: Array<{
    isSpend?: boolean;
    spendAmount?: number;
    spendCurrency?: string;
    actionDigest?: string;
  }>,
): SpendReviewConfig | undefined {
  if (!Array.isArray(reviewConfigs)) {
    return undefined;
  }
  return reviewConfigs.find((cfg) => cfg?.isSpend === true);
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
  allow_always?: AllowAlwaysValue;
  ttl_seconds?: number;
  allow_domain?: boolean;
  grant_directory?: boolean;
  grant_directory_path?: string;
  grant_directory_writable?: boolean;
  action_digest?: string;
  actionDigest?: string;
}

/**
 * [INPUT] Decision type + optional edited args / feedback / allow flags
 * [OUTPUT] LangGraph-compatible approval decision object
 * [POS] Shared payload builder for single and bulk approval resume
 */
export function resumeDecisionsIncludeDirectoryGrant(decisions: ApprovalDecision[]): boolean {
  return decisions.some(
    (decision) =>
      (decision.type === 'approve' || decision.type === 'edit') && decision.extensions.grantDirectory === true,
  );
}

/** Optimistic root for path-ASK grantDirectory when GET may lag behind persist. */
export function extractDirectoryGrantOptimistic(decisions: ApprovalDecision[]): DirectoryGrantOptimistic | undefined {
  for (const decision of decisions) {
    const meta = decision.extensions.grantDirectoryMeta;
    if (
      (decision.type === 'approve' || decision.type === 'edit') &&
      decision.extensions.grantDirectory &&
      meta?.path?.trim()
    ) {
      return {
        path: meta.path.trim(),
        writable: meta.writable,
        source: 'path_ask_grant',
      };
    }
  }
  return undefined;
}

export function buildApprovalDecision(decision: DecisionType, extra?: ToolApprovalResolveExtra): ApprovalDecision {
  const allowAlwaysVal = extra?.allow_always ?? false;
  const ttlFromAllowAlways =
    typeof allowAlwaysVal === 'object' && allowAlwaysVal !== null && 'ttl_seconds' in allowAlwaysVal
      ? allowAlwaysVal.ttl_seconds
      : undefined;
  const effectiveTtl = extra?.ttl_seconds ?? ttlFromAllowAlways;
  const resolvedDigest = extra?.action_digest || extra?.actionDigest;

  return {
    type: decision,
    args: extra?.edited_args,
    feedback: extra?.feedback,
    ...(extra?.guidance && { guidance: extra.guidance }),
    ...(resolvedDigest && { action_digest: resolvedDigest, actionDigest: resolvedDigest }),
    extensions: {
      allowAlways: allowAlwaysVal,
      ...(effectiveTtl !== undefined && { ttlSeconds: effectiveTtl }),
      ...(extra?.allow_domain && { allowDomain: true }),
      ...(resolvedDigest && { actionDigest: resolvedDigest, action_digest: resolvedDigest }),
      ...(extra?.grant_directory && {
        grantDirectory: true,
        ...(extra.grant_directory_path && {
          grantDirectoryMeta: {
            path: extra.grant_directory_path,
            writable: extra.grant_directory_writable ?? false,
          },
        }),
      }),
    },
  };
}
