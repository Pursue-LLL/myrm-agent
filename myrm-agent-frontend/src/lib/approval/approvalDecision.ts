import type { AllowAlwaysValue } from '@/lib/approval/allowAlwaysScope';
import type { SessionAccessRoot } from '@/store/chat/types/sessionAccess';
import type { ApprovalGrantDirectory } from '@/store/chat/types/toolApproval';

type DecisionType = 'approve' | 'edit' | 'reject';

export interface ApprovalDecision {
  type: DecisionType;
  args?: Record<string, unknown>;
  feedback?: string;
  guidance?: string;
  action_digest?: string;
  actionDigest?: string;
  ephemeral_credential_handles?: string[];
  extensions: {
    allowAlways: AllowAlwaysValue;
    ttlSeconds?: number;
    allowDomain?: boolean;
    grantDirectory?: boolean;
    grantDirectories?: ApprovalGrantDirectory[];
    actionDigest?: string;
    action_digest?: string;
    ephemeralCredentialHandles?: string[];
  };
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
  /** Folders the user chose to also grant: the ones the approval card offered */
  grant_directories?: ApprovalGrantDirectory[];
  action_digest?: string;
  actionDigest?: string;
  ephemeral_credential_handles?: string[];
}

/** True when an approved decision asks the server to persist its folder grants. */
export function resumeDecisionsIncludeDirectoryGrant(decisions: ApprovalDecision[]): boolean {
  return decisions.some((decision) => decision.type === 'approve' && decision.extensions.grantDirectory === true);
}

/** Roots to show at once after a grant, while the chat row may still lag behind the persist. */
export function extractDirectoryGrantOptimistic(decisions: ApprovalDecision[]): SessionAccessRoot[] {
  const roots = new Map<string, SessionAccessRoot>();
  for (const decision of decisions) {
    if (decision.type !== 'approve' || !decision.extensions.grantDirectory) {
      continue;
    }
    for (const { path, writable } of decision.extensions.grantDirectories ?? []) {
      roots.set(path, { path, writable, source: 'path_ask_grant' });
    }
  }
  return [...roots.values()];
}

/**
 * [INPUT] Decision type + optional edited args / feedback / allow flags
 * [OUTPUT] LangGraph-compatible approval decision object
 * [POS] Shared payload builder for single and bulk approval resume
 */
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
    ...(extra?.ephemeral_credential_handles && {
      ephemeral_credential_handles: extra.ephemeral_credential_handles,
    }),
    extensions: {
      allowAlways: allowAlwaysVal,
      ...(effectiveTtl !== undefined && { ttlSeconds: effectiveTtl }),
      ...(extra?.allow_domain && { allowDomain: true }),
      ...(resolvedDigest && { actionDigest: resolvedDigest, action_digest: resolvedDigest }),
      ...(extra?.ephemeral_credential_handles && {
        ephemeralCredentialHandles: extra.ephemeral_credential_handles,
      }),
      ...(extra?.grant_directories?.length ? { grantDirectory: true, grantDirectories: extra.grant_directories } : {}),
    },
  };
}
