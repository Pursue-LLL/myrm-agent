/**
 * [INPUT]
 * None - Pure TypeScript Contract definitions.
 *
 * [OUTPUT]
 * - HitlRiskLevel, HitlDecisionType, HitlApprovalPayload, HitlDecisionResult
 * - MobileVoiceStagedInputProps, MobileHitlApprovalCardProps
 *
 * [POS]
 * Type contracts for Mobile Remote Companion and Touch-Optimized HITL Cockpit.
 */

export type HitlRiskLevel = 'low' | 'medium' | 'high' | 'critical';

export type HitlDecisionType = 'approve' | 'reject' | 'steer';

export interface HitlApprovalPayload {
  requestId: string;
  actionTitle: string;
  commandOrTool: string;
  scopeDescription: string;
  riskLevel: HitlRiskLevel;
  rawParams?: Record<string, string | number | boolean>;
  timestamp?: string;
}

export interface HitlDecisionResult {
  requestId: string;
  decision: HitlDecisionType;
  reason?: string;
  steerInstruction?: string;
}

export interface MobileVoiceStagedInputProps {
  isOpen: boolean;
  onClose: () => void;
  onSend: (text: string) => void;
  className?: string;
}

export interface MobileHitlApprovalCardProps {
  payload: HitlApprovalPayload;
  onDecision: (result: HitlDecisionResult) => Promise<void> | void;
  isProcessing?: boolean;
  className?: string;
}
